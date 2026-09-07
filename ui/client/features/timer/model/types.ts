export interface TimerState {
	isRunning: boolean;
	selectedProjectId: string | null;
	elapsedSeconds: number;
	customStartTime: string | null;
}

export interface TimerStatus {
	isBeating: boolean;
	project: string | null;
	since: string | null;
	soFar: string | null;
}
