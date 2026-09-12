/**
 * Zod schemas for runtime API response validation
 * These schemas validate data from the backend API and provide type safety at runtime.
 */
import { z } from "zod";

// API Response Schemas (raw backend responses)

export const GoalOverrideSchema = z.object({
	week_of: z.string().nullable().optional(),
	effective_from: z.string().nullable().optional(),
	weekly_goal: z.number().nullable(),
	goal_type: z.enum(["target", "cap"]).nullable().optional(),
	note: z.string().nullable().optional(),
});

export type ApiGoalOverride = z.infer<typeof GoalOverrideSchema>;

// Work contracts (docs/work-contracts-roadmap.md). These mirror the API's
// `ProjectKind`, `ScheduleType`, `ContractTerm`, `Contract`, `AbsenceType`,
// `Holiday` and `Region` schemas field for field; the validators behind
// them (which numbers a schedule type needs, terms in order) are the API's,
// and a 422 names the offending path in `fields`.

export const ProjectKindSchema = z.enum(["day_job", "freelance", "side_project"]);
export type ApiProjectKind = z.infer<typeof ProjectKindSchema>;

export const ScheduleTypeSchema = z.enum(["full_time", "part_time", "custom", "objective"]);

export const ContractTermSchema = z.object({
	effective_from: z.string(), // YYYY-MM-DD
	schedule_type: ScheduleTypeSchema,
	full_time_hours: z.number().nullable().optional(),
	percentage: z.number().nullable().optional(), // fraction in (0, 1]
	weekly_hours: z.number().nullable().optional(),
	note: z.string().nullable().optional(),
});

export type ApiContractTerm = z.infer<typeof ContractTermSchema>;

export const ContractSchema = z.object({
	terms: z.array(ContractTermSchema),
	holiday_country: z.string().nullable().optional(),
	holiday_subdivision: z.string().nullable().optional(),
	opening_balance_hours: z.number().optional().default(0),
	ended_on: z.string().nullable().optional(),
});

export type ApiContract = z.infer<typeof ContractSchema>;

export const AbsenceTypeSchema = z.enum(["vacation", "sick", "other"]);

export const ApiAbsenceSchema = z.object({
	id: z.string(),
	project_id: z.string(),
	date: z.string(), // YYYY-MM-DD
	half_day: z.boolean().optional().default(false),
	type: AbsenceTypeSchema,
	note: z.string().nullable().optional(),
});

export type ApiAbsence = z.infer<typeof ApiAbsenceSchema>;
export const ApiAbsenceListSchema = z.array(ApiAbsenceSchema);

// One week of a day job against its contract (GET /contract/week). `expected`,
// `remaining` and `balance` are null — not 0 — when no time-based term is in
// force (an objective term, a week before the contract); 0 is a week the
// contract owed nothing by circumstance. `balance` is as of today whatever
// week is asked for.

export const DayAbsenceSchema = z.object({
	type: AbsenceTypeSchema,
	half_day: z.boolean(),
	note: z.string().nullable().optional(),
});

export const ContractDaySchema = z.object({
	date: z.string(), // YYYY-MM-DD
	expected: z.number(),
	worked: z.number(),
	holiday: z.string().nullable().optional(),
	absence: DayAbsenceSchema.nullable().optional(),
});

export type ApiContractDay = z.infer<typeof ContractDaySchema>;

export const ContractWeekSchema = z.object({
	week_of: z.string(), // the Monday, YYYY-MM-DD
	expected: z.number().nullable(),
	worked: z.number(),
	remaining: z.number().nullable(),
	balance: z.number().nullable(),
	days: z.array(ContractDaySchema),
});

export type ApiContractWeek = z.infer<typeof ContractWeekSchema>;

export const HolidaySchema = z.object({
	date: z.string(), // YYYY-MM-DD
	name: z.string(),
});

export const HolidayListSchema = z.array(HolidaySchema);

export const SubdivisionSchema = z.object({
	code: z.string(),
	name: z.string(),
});

export const RegionSchema = z.object({
	code: z.string(), // ISO 3166-1 alpha-2
	name: z.string(),
	subdivisions: z.array(SubdivisionSchema),
});

export const RegionListSchema = z.array(RegionSchema);

export const ApiProjectSchema = z.object({
	id: z.string().nullable().optional(),
	name: z.string(),
	description: z.string().nullable().optional(),
	color: z.string().nullable().optional(),
	archived: z.boolean().optional().default(false),
	weekly_goal: z.number().nullable().optional(),
	goal_type: z.enum(["target", "cap"]).optional().default("target"),
	goal_overrides: z.array(GoalOverrideSchema).optional().default([]),
	// P1.1: previously stripped by parseApiResponse — the wire now carries
	// these (P0.1 expanded ProjectResponse), so accept them on the way in.
	github_repo: z.string().nullable().optional(),
	category: z.string().nullable().optional(),
	autostart_repos: z.array(z.string()).optional().default([]),
	// A contract is read only on a day job; on any other kind it is null.
	kind: ProjectKindSchema.optional().default("side_project"),
	contract: ContractSchema.nullable().optional(),
});

export type ApiProject = z.infer<typeof ApiProjectSchema>;

/**
 * The list-endpoint item — same fields as ApiProject plus optional
 * aggregation slots populated when GET /api/projects/?include=... is sent.
 * P3.0 of the project-management revamp: collapses the previous N+1 fan-out
 * (one fetchProjectTotal + fetchProjectWeek per project) into one round-trip.
 */
export const ApiProjectListItemSchema = ApiProjectSchema.extend({
	total_minutes: z.number().nullable().optional(),
	weekly_minutes: z.number().nullable().optional(),
	effective_goal: z.number().nullable().optional(),
	effective_goal_type: z.enum(["target", "cap"]).nullable().optional(),
	effective_goal_overridden: z.boolean().nullable().optional(),
	// The current week against the contract, on a day job that has one; what
	// GET /contract/week reports, so the index can show it without a fan-out.
	// Null elsewhere, and all but contract_worked null under an objective term.
	contract_expected: z.number().nullable().optional(),
	contract_worked: z.number().nullable().optional(),
	contract_remaining: z.number().nullable().optional(),
	balance: z.number().nullable().optional(),
	last_tracked_at: z.string().nullable().optional(),
});

export type ApiProjectListItem = z.infer<typeof ApiProjectListItemSchema>;

export const ApiBeatSchema = z.object({
	id: z.string().nullable().optional(),
	start: z.string(), // ISO datetime
	end: z.string().nullable().optional(), // ISO datetime
	project_id: z.string().nullable().optional(),
	note: z.string().nullable().optional(),
	tags: z.array(z.string()).optional().default([]),
});

export type ApiBeat = z.infer<typeof ApiBeatSchema>;

export const TimerStatusSchema = z.object({
	isBeating: z.boolean(),
	project: ApiProjectSchema.nullable().optional(),
	since: z.string().nullable().optional(), // ISO datetime
	so_far: z.string().nullable().optional(), // Duration string like "0:14:25.297277"
});

export type TimerStatus = z.infer<typeof TimerStatusSchema>;

export const WeekBreakdownSchema = z.object({
	Monday: z.string().optional().default("0:00:00"),
	Tuesday: z.string().optional().default("0:00:00"),
	Wednesday: z.string().optional().default("0:00:00"),
	Thursday: z.string().optional().default("0:00:00"),
	Friday: z.string().optional().default("0:00:00"),
	Saturday: z.string().optional().default("0:00:00"),
	Sunday: z.string().optional().default("0:00:00"),
	total_hours: z.number().default(0),
	week_start: z.string().optional(),
	effective_goal: z.number().nullable().optional(),
	effective_goal_type: z.enum(["target", "cap"]).nullable().optional(),
	effective_goal_overridden: z.boolean().optional().default(false),
});

export type WeekBreakdown = z.infer<typeof WeekBreakdownSchema>;

export const ProjectTotalSchema = z.object({
	total_minutes: z.number().optional(),
	durations_per_month: z.record(z.string(), z.number()).optional(),
});

export type ProjectTotal = z.infer<typeof ProjectTotalSchema>;

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

/**
 * One flow-state window from the daemon's signal collector. Each window
 * is typically 1 minute of aggregated desktop activity. The composite
 * `flow_score` is a weighted blend of cadence, coherence, and category
 * fit — see the daemon's collector/scorer.go.
 */
export const FlowWindowSchema = z.object({
	id: z.string(),
	window_start: z.string(),
	window_end: z.string(),
	flow_score: z.number(),
	cadence_score: z.number(),
	coherence_score: z.number(),
	category_fit_score: z.number(),
	idle_fraction: z.number(),
	dominant_bundle_id: z.string(),
	dominant_category: z.string(),
	context_switches: z.number(),
	active_project_id: z.string().nullable(),
	editor_repo: z.string().nullable().optional(),
	editor_branch: z.string().nullable().optional(),
	editor_language: z.string().nullable().optional(),
});

export type FlowWindow = z.infer<typeof FlowWindowSchema>;

export const FlowWindowListSchema = z.array(FlowWindowSchema);

/** One bucket inside FlowWindowSummary — the highest-count entry on
 * its grouping axis (top_repo / top_language / top_bundle). */
export const FlowTopBucketSchema = z.object({
	key: z.string(),
	avg: z.number(),
	count: z.number(),
});
export type FlowTopBucket = z.infer<typeof FlowTopBucketSchema>;

/** Aggregate stats for a flow-window slice, returned in a single
 * round-trip by GET /api/signals/flow-windows/summary. Mirrors the
 * Python FlowWindowSummaryResponse. */
export const FlowWindowSummarySchema = z.object({
	count: z.number(),
	avg: z.number(),
	peak: z.number(),
	peak_at: z.string().nullable(),
	top_repo: FlowTopBucketSchema.nullable(),
	top_language: FlowTopBucketSchema.nullable(),
	top_bundle: FlowTopBucketSchema.nullable(),
});
export type FlowWindowSummary = z.infer<typeof FlowWindowSummarySchema>;

export const ProductivityScoreSchema = z.object({
	score: z.number(),
	components: z.object({
		consistency: z.number(),
		goals: z.number(),
		quality: z.number(),
	}),
});

export type ProductivityScore = z.infer<typeof ProductivityScoreSchema>;

export const ScoreHistoryItemSchema = z.object({
	week_of: z.string(),
	score: z.number(),
});

export type ScoreHistoryItem = z.infer<typeof ScoreHistoryItemSchema>;

export const ScoreHistorySchema = z.array(ScoreHistoryItemSchema);

export const ProjectBreakdownEntrySchema = z.object({
	project_id: z.string(),
	name: z.string(),
	hours: z.number(),
});

export type ProjectBreakdownEntry = z.infer<typeof ProjectBreakdownEntrySchema>;

export const WeeklyDigestSchema = z.object({
	id: z.string().nullable().optional(),
	week_of: z.string(),
	generated_at: z.string(),
	total_hours: z.number(),
	session_count: z.number(),
	active_days: z.number(),
	top_project_id: z.string().nullable().optional(),
	top_project_name: z.string().nullable().optional(),
	top_project_hours: z.number().default(0),
	vs_last_week_pct: z.number().nullable().optional(),
	longest_day: z.string().nullable().optional(),
	longest_day_hours: z.number().default(0),
	best_streak: z.number().default(0),
	observation: z.string().default(""),
	project_breakdown: z.array(ProjectBreakdownEntrySchema).default([]),
	productivity_score: z.number().default(0),
});

export type WeeklyDigest = z.infer<typeof WeeklyDigestSchema>;

export const WeeklyDigestListSchema = z.array(WeeklyDigestSchema);

export const InsightCardSchema = z.object({
	id: z.string(),
	type: z.string(),
	title: z.string(),
	body: z.string(),
	data: z.record(z.string(), z.unknown()).default({}),
	priority: z.number().default(3),
});

export type InsightCard = z.infer<typeof InsightCardSchema>;

export const PatternsResponseSchema = z.object({
	insights: z.array(InsightCardSchema),
	generated_at: z.string(),
});

export type PatternsResponse = z.infer<typeof PatternsResponseSchema>;

export const FocusScoreSchema = z.object({
	beat_id: z.string(),
	score: z.number(),
	components: z.object({
		length: z.number(),
		peak_hours: z.number(),
		fragmentation: z.number(),
	}),
});

export type FocusScore = z.infer<typeof FocusScoreSchema>;

export const FocusScoreListSchema = z.array(FocusScoreSchema);

export const ProjectHealthSchema = z.object({
	project_id: z.string(),
	project_name: z.string(),
	days_since_last: z.number().nullable().optional(),
	weekly_goal_trend: z.array(z.number()).default([]),
	avg_session_length_trend: z.array(z.number()).default([]),
	alert: z.string().nullable().optional(),
});

export type ProjectHealth = z.infer<typeof ProjectHealthSchema>;

export const ProjectHealthListSchema = z.array(ProjectHealthSchema);

export const CalendarStatusSchema = z.object({
	connected: z.boolean(),
	provider: z.string().nullable().optional(),
});

export type CalendarStatus = z.infer<typeof CalendarStatusSchema>;

export const GitHubStatusSchema = z.object({
	connected: z.boolean(),
	github_username: z.string().nullable().optional(),
});

export type GitHubStatus = z.infer<typeof GitHubStatusSchema>;

export const GitCommitDaySchema = z.object({
	date: z.string(),
	commit_count: z.number(),
});

export type GitCommitDay = z.infer<typeof GitCommitDaySchema>;

export const GitCommitActivitySchema = z.array(GitCommitDaySchema);

export const GapSchema = z.object({
	start: z.string(),
	end: z.string(),
	duration_minutes: z.number(),
});

export type Gap = z.infer<typeof GapSchema>;

export const GapListSchema = z.array(GapSchema);

// Array schemas for list endpoints

export const ApiProjectListSchema = z.array(ApiProjectListItemSchema);
export const ApiBeatListSchema = z.array(ApiBeatSchema);

// Validation helpers

/**
 * Safely parse API response with a schema, returning parsed data or throwing
 */
export function parseApiResponse<T>(schema: z.ZodSchema<T>, data: unknown): T {
	return schema.parse(data);
}
