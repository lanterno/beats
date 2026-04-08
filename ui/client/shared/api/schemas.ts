/**
 * Zod schemas for runtime API response validation
 * These schemas validate data from the backend API and provide type safety at runtime.
 */
import { z } from "zod";

// ============================================================================
// API Response Schemas (raw backend responses)
// ============================================================================

/**
 * Goal override for a specific week or date range
 */
export const GoalOverrideSchema = z.object({
	week_of: z.string().nullable().optional(),
	effective_from: z.string().nullable().optional(),
	weekly_goal: z.number(),
	goal_type: z.enum(["target", "cap"]).nullable().optional(),
	note: z.string().nullable().optional(),
});

export type ApiGoalOverride = z.infer<typeof GoalOverrideSchema>;

/**
 * Project as returned by the API
 */
export const ApiProjectSchema = z.object({
	id: z.string().nullable().optional(),
	name: z.string(),
	description: z.string().nullable().optional(),
	estimation: z.string().nullable().optional(),
	color: z.string().nullable().optional(),
	archived: z.boolean().optional().default(false),
	weekly_goal: z.number().nullable().optional(),
	goal_type: z.enum(["target", "cap"]).optional().default("target"),
	goal_overrides: z.array(GoalOverrideSchema).optional().default([]),
});

export type ApiProject = z.infer<typeof ApiProjectSchema>;

/**
 * Beat (work session) as returned by the API
 */
export const ApiBeatSchema = z.object({
	id: z.string().nullable().optional(),
	start: z.string(), // ISO datetime
	end: z.string().nullable().optional(), // ISO datetime
	project_id: z.string().nullable().optional(),
	note: z.string().nullable().optional(),
	tags: z.array(z.string()).optional().default([]),
});

export type ApiBeat = z.infer<typeof ApiBeatSchema>;

/**
 * Timer status as returned by the API
 */
export const TimerStatusSchema = z.object({
	isBeating: z.boolean(),
	project: ApiProjectSchema.nullable().optional(),
	since: z.string().nullable().optional(), // ISO datetime
	so_far: z.string().nullable().optional(), // Duration string like "0:14:25.297277"
});

export type TimerStatus = z.infer<typeof TimerStatusSchema>;

/**
 * Week breakdown response from project week endpoint
 */
export const WeekBreakdownSchema = z.object({
	Monday: z.string().optional().default("0:00:00"),
	Tuesday: z.string().optional().default("0:00:00"),
	Wednesday: z.string().optional().default("0:00:00"),
	Thursday: z.string().optional().default("0:00:00"),
	Friday: z.string().optional().default("0:00:00"),
	Saturday: z.string().optional().default("0:00:00"),
	Sunday: z.string().optional().default("0:00:00"),
	total_hours: z.number().default(0),
	effective_goal: z.number().nullable().optional(),
	effective_goal_type: z.enum(["target", "cap"]).nullable().optional(),
});

export type WeekBreakdown = z.infer<typeof WeekBreakdownSchema>;

/**
 * Project total response
 */
export const ProjectTotalSchema = z.object({
	total_minutes: z.number().optional(),
	durations_per_month: z.record(z.string(), z.number()).optional(),
});

export type ProjectTotal = z.infer<typeof ProjectTotalSchema>;

// ============================================================================
// Analytics schemas
// ============================================================================

export const HeatmapDaySchema = z.object({
	date: z.string(),
	total_minutes: z.number(),
	session_count: z.number(),
	project_count: z.number(),
});

export type HeatmapDay = z.infer<typeof HeatmapDaySchema>;

export const RhythmSlotSchema = z.object({
	slot: z.number(),
	minutes: z.number(),
});

export type RhythmSlot = z.infer<typeof RhythmSlotSchema>;

export const HeatmapDayListSchema = z.array(HeatmapDaySchema);
export const RhythmSlotListSchema = z.array(RhythmSlotSchema);

// ============================================================================
// Intention schemas
// ============================================================================

export const IntentionSchema = z.object({
	id: z.string(),
	project_id: z.string(),
	date: z.string(),
	planned_minutes: z.number(),
	completed: z.boolean(),
});

export type Intention = z.infer<typeof IntentionSchema>;

export const IntentionListSchema = z.array(IntentionSchema);

// ============================================================================
// DailyNote schemas
// ============================================================================

export const DailyNoteSchema = z.object({
	id: z.string(),
	date: z.string(),
	note: z.string(),
	mood: z.number().nullable().optional(),
	created_at: z.string(),
});

export type DailyNote = z.infer<typeof DailyNoteSchema>;

// ============================================================================
// Array schemas for list endpoints
// ============================================================================

export const ApiProjectListSchema = z.array(ApiProjectSchema);
export const ApiBeatListSchema = z.array(ApiBeatSchema);

// ============================================================================
// Validation helpers
// ============================================================================

/**
 * Safely parse API response with a schema, returning parsed data or throwing
 */
export function parseApiResponse<T>(schema: z.ZodSchema<T>, data: unknown): T {
	return schema.parse(data);
}

/**
 * Safely parse API response, returning result object instead of throwing
 */
export function safeParseApiResponse<T>(
	schema: z.ZodSchema<T>,
	data: unknown,
): { success: true; data: T } | { success: false; error: z.ZodError } {
	const result = schema.safeParse(data);
	if (result.success) {
		return { success: true, data: result.data };
	}
	return { success: false, error: result.error };
}
