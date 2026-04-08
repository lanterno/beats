/**
 * Project Domain Types
 * Pure domain types with no external dependencies.
 */

/**
 * A per-week or date-range override of a project's weekly goal.
 */
export interface GoalOverride {
	weekOf?: string; // ISO date string of Monday, for one-off
	effectiveFrom?: string; // ISO date string, for permanent
	weeklyGoal: number;
	goalType?: "target" | "cap";
	note?: string;
}

/**
 * Core Project entity
 */
export interface Project {
	id: string;
	name: string;
	description?: string;
	color: string;
	archived: boolean;
	estimation?: string;
	weeklyGoal?: number; // Weekly goal in hours
	goalType?: "target" | "cap";
	goalOverrides: GoalOverride[];
}

/**
 * Project with calculated total time
 */
export interface ProjectWithDuration extends Project {
	totalMinutes: number;
	weeklyMinutes: number;
	effectiveGoal?: number; // Resolved goal for current week
	effectiveGoalType?: "target" | "cap";
}

/**
 * Daily summary for a project
 */
export interface DailySummary {
	day: string;
	hours: number;
	date: Date;
	totalMinutes: number;
	sessionCount: number;
}

/**
 * Weekly hours data for a project
 */
export interface WeekHours {
	weeksAgo: number;
	hours: number;
	dailyDurations: Record<string, string>;
	effectiveGoal?: number;
	effectiveGoalType?: "target" | "cap";
}
