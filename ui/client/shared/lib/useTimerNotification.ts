/**
 * Timer Notification Hook
 * Sends a browser notification when the timer has been running for too long.
 * Default threshold: 2 hours. Repeats every hour after that.
 */
import { useEffect, useRef } from "react";

const THRESHOLD_MS = 2 * 60 * 60 * 1000; // 2 hours
const REPEAT_MS = 60 * 60 * 1000; // remind every hour after

function requestPermission() {
	if ("Notification" in window && Notification.permission === "default") {
		Notification.requestPermission();
	}
}

export function useTimerNotification(
	isRunning: boolean,
	elapsedSeconds: number,
	projectName: string | undefined,
) {
	const lastNotifiedAt = useRef<number>(0);

	// Ask for permission when timer first starts
	useEffect(() => {
		if (isRunning) requestPermission();
	}, [isRunning]);

	useEffect(() => {
		if (!isRunning || !projectName) {
			lastNotifiedAt.current = 0;
			return;
		}

		const elapsedMs = elapsedSeconds * 1000;
		if (elapsedMs < THRESHOLD_MS) return;

		// Determine if we should notify
		const sinceLastNotification = elapsedMs - lastNotifiedAt.current;
		const shouldNotify =
			lastNotifiedAt.current === 0 ? elapsedMs >= THRESHOLD_MS : sinceLastNotification >= REPEAT_MS;

		if (shouldNotify && "Notification" in window && Notification.permission === "granted") {
			const hours = Math.floor(elapsedSeconds / 3600);
			const mins = Math.floor((elapsedSeconds % 3600) / 60);
			const timeStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;

			new Notification("Timer still running", {
				body: `You've been working on ${projectName} for ${timeStr}. Still going?`,
				icon: "/pwa-192.svg",
				tag: "beats-timer-reminder",
			} as NotificationOptions);
			lastNotifiedAt.current = elapsedMs;
		}
	}, [isRunning, elapsedSeconds, projectName]);
}
