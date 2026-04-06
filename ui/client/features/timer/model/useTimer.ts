/**
 * Timer State Management Hook
 * Manages timer state with API sync and localStorage persistence.
 */
import { useEffect, useState, useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { projectKeys } from "@/entities/project";
import { sessionKeys } from "@/entities/session";
import { fetchTimerStatus, startTimerApi, stopTimerApi } from "../api";
import type { TimerState } from "./types";
import { parseUtcIso } from "@/shared/lib";

const STORAGE_KEY = "project_hours_timer";
const STATUS_POLL_INTERVAL = 2000;

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

  // Poll timer status from API
  useEffect(() => {
    let pollInterval: NodeJS.Timeout | null = null;

    const pollTimerStatus = async () => {
      try {
        const status = await fetchTimerStatus();

        if (status.isBeating && status.since && status.project?.id) {
          const startTime = parseUtcIso(status.since);
          const now = new Date();
          const elapsedSeconds = Math.floor((now.getTime() - startTime.getTime()) / 1000);

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
      } catch (error) {
        console.error("Error polling timer status:", error);
        isSyncingFromApiRef.current = false;
      }
    };

    // Initial fetch
    pollTimerStatus();

    // Set up polling interval
    pollInterval = setInterval(pollTimerStatus, STATUS_POLL_INTERVAL);

    return () => {
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, []);

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
  }, [timerState.isRunning, timerState.customStartTime]);

  const startTimer = useCallback(async (projectId: string, startTime?: string) => {
    const timerStartTime = startTime || new Date().toISOString();

    try {
      await startTimerApi(projectId, timerStartTime);

      setTimerState({
        isRunning: true,
        selectedProjectId: projectId,
        elapsedSeconds: 0,
        customStartTime: timerStartTime,
      });
      apiStartTimeRef.current = timerStartTime;
    } catch (error) {
      console.error("Error starting timer:", error);
      // Still update local state even if API call fails
      setTimerState({
        isRunning: true,
        selectedProjectId: projectId,
        elapsedSeconds: 0,
        customStartTime: timerStartTime,
      });
    }
  }, []);

  const stopTimer = useCallback(async () => {
    const currentState = timerState;
    if (!currentState.isRunning || !currentState.selectedProjectId) {
      return;
    }

    const stopTime = new Date().toISOString();

    try {
      await stopTimerApi(stopTime);

      // Invalidate queries to refetch fresh data
      queryClient.invalidateQueries({ queryKey: projectKeys.all });
      queryClient.invalidateQueries({ queryKey: sessionKeys.all });

      setTimerState({
        isRunning: false,
        selectedProjectId: null,
        elapsedSeconds: 0,
        customStartTime: null,
      });
      apiStartTimeRef.current = null;
    } catch (error) {
      console.error("Error stopping timer:", error);
      setTimerState({
        isRunning: false,
        selectedProjectId: null,
        elapsedSeconds: 0,
        customStartTime: null,
      });
      apiStartTimeRef.current = null;
    }
  }, [timerState, queryClient]);

  const selectProject = useCallback((projectId: string | null) => {
    setTimerState((prev) => ({ ...prev, selectedProjectId: projectId }));
  }, []);

  const setCustomStartTime = useCallback((startTime: string | null) => {
    setTimerState((prev) => ({ ...prev, customStartTime: startTime }));
  }, []);

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
