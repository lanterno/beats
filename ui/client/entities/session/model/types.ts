/**
 * Session Domain Types
 * Pure domain types for work sessions (beats).
 */

export interface Session {
	id: string;
	projectId: string;
	startTime: string; // ISO string
	endTime: string; // ISO string
	duration: number; // in minutes
	note?: string;
	tags: string[];
}

export interface DaySummary {
	date: Date;
	dayName: string;
	dateShort: string;
	totalMinutes: number;
	sessionCount: number;
}

/**
 * A segment of time within a day attributed to a specific project (for stacked charts)
 */
export interface DayProjectSegment {
	projectId: string;
	projectName: string;
	projectColor: string;
	minutes: number;
}

/**
 * Full breakdown of a single day's time across projects
 */
export interface DayProjectBreakdown {
	date: Date;
	dayName: string;
	isToday: boolean;
	segments: DayProjectSegment[];
	totalMinutes: number;
}

export interface ProjectOption {
	id: string;
	name: string;
}
