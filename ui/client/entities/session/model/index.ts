/**
 * Session model - public API
 */

// Types
export type { Session, DaySummary, DayProjectBreakdown, DayProjectSegment, ProjectOption } from "./types";

// Mappers
export { toSession, toApiBeat, calculateDuration } from "./mappers";
