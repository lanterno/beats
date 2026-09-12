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

/** What a project is to the person tracking it. A contract is read only on a day job. */
export type ProjectKind = "day_job" | "freelance" | "side_project";

/**
 * How a contract term states the hours it owes. `full_time` and `part_time`
 * owe `fullTimeHours × percentage`; `custom` states `weeklyHours` outright;
 * `objective` owes nothing and has no balance (the personal goal applies).
 */
export type ScheduleType = "full_time" | "part_time" | "custom" | "objective";

/** One stretch of a contract, from `effectiveFrom` until the next term takes over. */
export interface ContractTerm {
	effectiveFrom: string; // YYYY-MM-DD, any weekday
	scheduleType: ScheduleType;
	fullTimeHours?: number; // basis for the time-based types
	percentage?: number; // fraction in (0, 1]; 1 for full_time
	weeklyHours?: number; // custom only
	note?: string;
}

/** A day job's terms as they changed over time, plus what frames them. */
export interface Contract {
	/** In ascending order of effectiveFrom, never empty. */
	terms: ContractTerm[];
	holidayCountry?: string; // ISO 3166-1 alpha-2, e.g. "CH"
	holidaySubdivision?: string; // ISO 3166-2 part, e.g. "ZH"
	/** Hours banked (or owed, if negative) before Beats started counting. */
	openingBalanceHours: number;
	/** Freezes the balance from this day on. */
	endedOn?: string;
}

/** An absence as the week route reports it on a day: what kind, and whether half of it. */
export interface ContractDayAbsence {
	type: "vacation" | "sick" | "other";
	halfDay: boolean;
	note?: string;
}

/** One day of a week against the contract. */
export interface ContractDay {
	date: string; // YYYY-MM-DD
	/** Hours the contract owed on this day, after its holiday or absence; 0 on a weekend. */
	expected: number;
	/** Hours worked, by the local day each beat started on. */
	worked: number;
	holiday?: string; // the holiday's name
	absence?: ContractDayAbsence;
}

/**
 * One week of a day job against its contract. `expected`, `remaining` and
 * `balance` are undefined — not 0 — when no time-based term is in force
 * (an objective term, a week before the contract); 0 means the contract
 * owed nothing by circumstance. `balance` is as of today whatever week
 * this is.
 */
export interface ContractWeek {
	weekOf: string; // the Monday, YYYY-MM-DD
	expected?: number;
	worked: number;
	remaining?: number;
	balance?: number;
	/** Monday to Sunday, in order. */
	days: ContractDay[];
}

/** One public holiday of the contract's region. */
export interface Holiday {
	date: string; // YYYY-MM-DD
	name: string;
}

/** One country in the region picker, with the subdivisions that change its calendar. */
export interface HolidayRegion {
	code: string;
	name: string;
	subdivisions: { code: string; name: string }[];
}

export interface Project {
	id: string;
	name: string;
	description?: string;
	color: string;
	archived: boolean;
	weeklyGoal?: number; // Weekly goal in hours
	goalType?: "target" | "cap";
	goalOverrides: GoalOverride[];
	/** GitHub repo in "owner/repo" format for commit correlation. */
	githubRepo?: string;
	/** Activity category — fuels the daemon's flow_score category_fit matcher. */
	category?: string;
	/** Absolute local repo paths the daemon auto-starts a timer for. */
	autostartRepos: string[];
	kind: ProjectKind;
	/** Only on a day job; a day job may still lack one ("leave first, contract later"). */
	contract?: Contract;
}

export interface ProjectWithDuration extends Project {
	totalMinutes: number;
	weeklyMinutes: number;
	/** number = goal applies; null = override says "no goal"; undefined = unknown */
	effectiveGoal?: number | null;
	effectiveGoalType?: "target" | "cap";
	/** True iff a goal override resolves for the current week */
	effectiveGoalOverridden?: boolean;
	/**
	 * The current week against the contract, on a day job that has one
	 * (see ContractWeek for what undefined means). `contractWorked` is the
	 * contract's figure — every beat by local day, a running timer included —
	 * where `weeklyMinutes` is the personal goal's: completed beats by UTC day.
	 */
	contractExpected?: number;
	contractWorked?: number;
	contractRemaining?: number;
	/** Running balance against the contract as of today: over if positive, owed if negative. */
	balance?: number;
	/** ISO timestamp of the project's most recent beat — drives the
	 *  /projects index page's "last tracked" column (P3.0). */
	lastTrackedAt?: string;
}

export interface DailySummary {
	day: string;
	hours: number;
	date: Date;
	totalMinutes: number;
	sessionCount: number;
}

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
	/**
	 * What the contract expects of this week after holidays and absences, on
	 * a day job it governs — the week card's figure. Undefined elsewhere, and
	 * on a week the contract expects nothing of by nature (a term of 0 hours).
	 */
	contractExpected?: number;
}
