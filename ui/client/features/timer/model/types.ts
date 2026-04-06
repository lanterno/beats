/**
 * Timer Feature Types
 */

/**
 * Timer state
 */
export interface TimerState {
  isRunning: boolean;
  selectedProjectId: string | null;
  elapsedSeconds: number;
  customStartTime: string | null;
}

/**
 * Timer status from API
 */
export interface TimerStatus {
  isBeating: boolean;
  project: string | null;
  since: string | null;
  soFar: string | null;
}
