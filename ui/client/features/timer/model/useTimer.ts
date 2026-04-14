/**
 * Timer State Management Hook
 * Manages timer state with API sync and localStorage persistence.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { projectKeys } from "@/entities/project";
import { sessionKeys } from "@/entities/session";
import { parseUtcIso, useOnlineStatus } from "@/shared/lib";
import { drainQueue, enqueueEvent } from "@/shared/lib/offlineQueue";
import { fetchTimerStatus, startTimerApi, stopTimerApi } from "../api";
import type { TimerState } from "./types";

const STORAGE_KEY = "project_hours_timer";
const TIMER_STATUS_KEY = ["timer", "status"] as const;
const REFETCH_WHILE_RUNNING_MS = 15_000;
const REFETCH_WHILE_IDLE_MS = 30_000;

/**
 * Timer management hook with API synchronization
 */
export function useTimer() {
	const queryClient = useQueryClient();

	const [timerState, setTimerState] = useState<TimerState>(() => {
		// Initialize with localStorage if available
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored) {
			try {
				return JSON.parse(stored);
			} catch {
				// Fall through to default
			}
		}
		return {
			isRunning: false,
			selectedProjectId: null,
			elapsedSeconds: 0,
			customStartTime: null,
		};
	});

	const apiStartTimeRef = useRef<string | null>(null);
	const isSyncingFromApiRef = useRef(false);

	// Fetch timer status from API. Interval adapts to running state and pauses
	// on hidden tabs; TanStack Query also refetches on focus / reconnect.
	const { data: status } = useQuery({
		queryKey: TIMER_STATUS_KEY,
		queryFn: fetchTimerStatus,
		refetchInterval: (query) =>
			query.state.data?.isBeating ? REFETCH_WHILE_RUNNING_MS : REFETCH_WHILE_IDLE_MS,
		refetchIntervalInBackground: false,
		refetchOnWindowFocus: true,
		refetchOnReconnect: true,
	});

	// Sync local state from fetched status
	useEffect(() => {
		if (!status) return;

		if (status.isBeating && status.since && status.project?.id) {
			const startTime = parseUtcIso(status.since);
			const elapsedSeconds = Math.floor((Date.now() - startTime.getTime()) / 1000);

			isSyncingFromApiRef.current = true;
			apiStartTimeRef.current = status.since;

			setTimerState({
				isRunning: true,
				selectedProjectId: status.project.id,
				elapsedSeconds,
				customStartTime: status.since,
			});

			queueMicrotask(() => {
				isSyncingFromApiRef.current = false;
			});
		} else {
			isSyncingFromApiRef.current = true;
			apiStartTimeRef.current = null;

			setTimerState((prev) => {
				if (prev.isRunning) {
					return {
						...prev,
						isRunning: false,
						selectedProjectId: null,
						elapsedSeconds: 0,
						customStartTime: null,
					};
				}
				return prev;
			});

			queueMicrotask(() => {
				isSyncingFromApiRef.current = false;
			});
		}
	}, [status]);

	// Update localStorage when timer state changes (but not from API sync)
	useEffect(() => {
		if (!isSyncingFromApiRef.current) {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(timerState));
		}
	}, [timerState]);

	// Timer interval - update elapsed seconds if timer is running
	useEffect(() => {
		if (!timerState.isRunning) return;

		const interval = setInterval(() => {
			setTimerState((prev) => {
				if (prev.customStartTime && apiStartTimeRef.current === prev.customStartTime) {
					const startTime = parseUtcIso(prev.customStartTime);
					const now = new Date();
					const elapsedSeconds = Math.floor((now.getTime() - startTime.getTime()) / 1000);
					return { ...prev, elapsedSeconds };
				}
				return { ...prev, elapsedSeconds: prev.elapsedSeconds + 1 };
			});
		}, 1000);

		return () => clearInterval(interval);
	}, [timerState.isRunning]);

	const startTimer = useCallback(
		async (projectId: string, startTime?: string) => {
			const timerStartTime = startTime || new Date().toISOString();

			setTimerState({
				isRunning: true,
				selectedProjectId: projectId,
				elapsedSeconds: 0,
				customStartTime: timerStartTime,
			});
			apiStartTimeRef.current = timerStartTime;

			try {
				await startTimerApi(projectId, timerStartTime);
				queryClient.invalidateQueries({ queryKey: TIMER_STATUS_KEY });
			} catch {
				await enqueueEvent({ type: "start", payload: { projectId, time: timerStartTime } });
			}
		},
		[queryClient],
	);

	const stopTimer = useCallback(
		async (customStopTime?: string) => {
			const currentState = timerState;
			if (!currentState.isRunning || !currentState.selectedProjectId) {
				return;
			}

			const stopTime = customStopTime || new Date().toISOString();

			setTimerState({
				isRunning: false,
				selectedProjectId: null,
				elapsedSeconds: 0,
				customStartTime: null,
			});
			apiStartTimeRef.current = null;

			try {
				await stopTimerApi(stopTime);
				queryClient.invalidateQueries({ queryKey: TIMER_STATUS_KEY });
				queryClient.invalidateQueries({ queryKey: projectKeys.all });
				queryClient.invalidateQueries({ queryKey: sessionKeys.all });
			} catch {
				await enqueueEvent({ type: "stop", payload: { time: stopTime } });
			}
		},
		[timerState, queryClient],
	);

	const selectProject = useCallback((projectId: string | null) => {
		setTimerState((prev) => ({ ...prev, selectedProjectId: projectId }));
	}, []);

	const setCustomStartTime = useCallback((startTime: string | null) => {
		setTimerState((prev) => ({ ...prev, customStartTime: startTime }));
	}, []);

	// Drain offline queue when connectivity returns
	const handleReconnect = useCallback(() => {
		drainQueue(async (event) => {
			if (event.type === "start" && event.payload.projectId) {
				await startTimerApi(event.payload.projectId, event.payload.time);
			} else if (event.type === "stop") {
				await stopTimerApi(event.payload.time);
			}
		}).then((count) => {
			if (count > 0) {
				queryClient.invalidateQueries({ queryKey: projectKeys.all });
				queryClient.invalidateQueries({ queryKey: sessionKeys.all });
			}
		});
	}, [queryClient]);
	useOnlineStatus(handleReconnect);

	return {
		isRunning: timerState.isRunning,
		selectedProjectId: timerState.selectedProjectId,
		elapsedSeconds: timerState.elapsedSeconds,
		customStartTime: timerState.customStartTime,
		startTimer,
		stopTimer,
		selectProject,
		setCustomStartTime,
	};
}
