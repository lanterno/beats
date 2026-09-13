/**
 * Timer Display Component
 * Shows the current timer value.
 */
import { Clock } from "lucide-react";
import { formatSecondsToTime, parseUtcIso } from "@/shared/lib";

interface TimerDisplayProps {
	elapsedSeconds: number;
	customStartTime: string | null;
	isRunning: boolean;
	projectName?: string;
}

export function TimerDisplay({
	elapsedSeconds,
	customStartTime,
	isRunning,
	projectName,
}: TimerDisplayProps) {
	// Calculate display time
	let totalSeconds = elapsedSeconds;

	if (customStartTime && isRunning) {
		const startDate = parseUtcIso(customStartTime);
		const now = new Date();
		totalSeconds = Math.floor((now.getTime() - startDate.getTime()) / 1000);
	}

	const displayTime = formatSecondsToTime(totalSeconds);

	return (
		<div className="flex flex-col items-center py-3">
			<div className="flex items-center gap-2 mb-1">
				<Clock className="w-4 h-4 text-muted-foreground" />
				<span className="font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
					Timer
				</span>
			</div>
			<p
				className={`font-heading text-4xl font-extrabold tracking-[-0.01em] ${isRunning ? "text-foreground" : "text-muted-foreground"}`}
			>
				{displayTime}
			</p>
			{projectName && isRunning && (
				<p className="text-muted-foreground text-base font-medium mt-2">{projectName}</p>
			)}
			{isRunning && customStartTime && (
				<p className="text-muted-foreground text-sm mt-1">
					Started{" "}
					{parseUtcIso(customStartTime).toLocaleString(undefined, {
						hour: "2-digit",
						minute: "2-digit",
						second: "2-digit",
						hour12: true,
					})}
				</p>
			)}
		</div>
	);
}
