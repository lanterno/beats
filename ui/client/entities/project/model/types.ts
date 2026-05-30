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
	weeklyGoal: number | null; // null = no goal for this window
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
	/** GitHub repo in "owner/repo" format for commit correlation. */
	githubRepo?: string;
	/** Activity category — fuels the daemon's flow_score category_fit matcher. */
	category?: string;
	/** Absolute local repo paths the daemon auto-starts a timer for. */
	autostartRepos: string[];
}

/**
 * Project with calculated total time
 */
export interface ProjectWithDuration extends Project {
	totalMinutes: number;
	weeklyMinutes: number;
	/** number = goal applies; null = override says "no goal"; undefined = unknown */
	effectiveGoal?: number | null;
	effectiveGoalType?: "target" | "cap";
	/** True iff a goal override resolves for the current week */
	effectiveGoalOverridden?: boolean;
	/** ISO timestamp of the project's most recent beat — drives the
	 *  /projects index page's "last tracked" column (P3.0). */
	lastTrackedAt?: string;
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
	/** Canonical Monday (ISO date) for this week, resolved server-side. */
	weekStart?: string;
	/** number = goal applies; null = override says "no goal"; undefined = unknown */
	effectiveGoal?: number | null;
	effectiveGoalType?: "target" | "cap";
	/** True iff a goal override resolves for this week */
	effectiveGoalOverridden?: boolean;
}
