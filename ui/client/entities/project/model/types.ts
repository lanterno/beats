/**
 * Project Domain Types
 * Pure domain types with no external dependencies.
 */

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
}

/**
 * Project with calculated total time
 */
export interface ProjectWithDuration extends Project {
	totalMinutes: number;
	weeklyMinutes: number;
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
}
