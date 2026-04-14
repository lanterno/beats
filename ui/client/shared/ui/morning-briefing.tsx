/**
 * Morning Briefing Overlay
 * Shown once per day on first open. Displays yesterday's summary,
 * today's intentions, and weekly goal warnings.
 */

import { Sunrise, X } from "lucide-react";
import { useEffect, useState } from "react";
import { formatDuration } from "@/shared/lib";

const BRIEFING_KEY = "beats_last_briefing_date";

interface MorningBriefingProps {
	yesterdayMinutes: number;
	yesterdaySessionCount: number;
	yesterdayTopProject?: string;
	todayIntentionCount: number;
	goalWarnings: Array<{ projectName: string; hoursRemaining: number; daysLeft: number }>;
}

export function MorningBriefing({
	yesterdayMinutes,
	yesterdaySessionCount,
	yesterdayTopProject,
	todayIntentionCount,
	goalWarnings,
}: MorningBriefingProps) {
	const [visible, setVisible] = useState(false);

	useEffect(() => {
		const today = new Date().toISOString().slice(0, 10);
		const last = localStorage.getItem(BRIEFING_KEY);
		if (last !== today) {
			// Show briefing after a short delay
			const timer = setTimeout(() => setVisible(true), 500);
			return () => clearTimeout(timer);
		}
	}, []);

	const dismiss = () => {
		setVisible(false);
		localStorage.setItem(BRIEFING_KEY, new Date().toISOString().slice(0, 10));
	};

	if (!visible) return null;

	return (
		<div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm">
			<div className="bg-card border border-border rounded-xl shadow-xl max-w-sm w-full mx-4 overflow-hidden">
				{/* Header */}
				<div className="flex items-center justify-between px-5 py-4 border-b border-border/40">
					<div className="flex items-center gap-2">
						<Sunrise className="w-5 h-5 text-accent" />
						<h2 className="text-base font-heading font-semibold text-foreground">Good morning</h2>
					</div>
					<button
						onClick={dismiss}
						className="p-1 rounded-md text-muted-foreground hover:text-foreground transition-colors"
					>
						<X className="w-4 h-4" />
					</button>
				</div>

				<div className="px-5 py-4 space-y-4">
					{/* Yesterday summary */}
					<div>
						<p className="text-xs uppercase tracking-[0.1em] text-muted-foreground mb-1.5">
							Yesterday
						</p>
						{yesterdaySessionCount > 0 ? (
							<p className="text-sm text-foreground">
								{formatDuration(yesterdayMinutes)} across {yesterdaySessionCount} session
								{yesterdaySessionCount !== 1 ? "s" : ""}
								{yesterdayTopProject && (
									<span className="text-muted-foreground">
										{" "}
										— top project: {yesterdayTopProject}
									</span>
								)}
							</p>
						) : (
							<p className="text-sm text-muted-foreground/70 italic">No sessions tracked</p>
						)}
					</div>

					{/* Today's intentions */}
					<div>
						<p className="text-xs uppercase tracking-[0.1em] text-muted-foreground mb-1.5">Today</p>
						<p className="text-sm text-foreground">
							{todayIntentionCount > 0
								? `${todayIntentionCount} intention${todayIntentionCount !== 1 ? "s" : ""} set`
								: "No intentions set yet — head to the dashboard to plan your day"}
						</p>
					</div>

					{/* Goal warnings */}
					{goalWarnings.length > 0 && (
						<div>
							<p className="text-xs uppercase tracking-[0.1em] text-accent mb-1.5">Goal alerts</p>
							<div className="space-y-1">
								{goalWarnings.map((w) => (
									<p key={w.projectName} className="text-sm text-foreground">
										<span className="font-medium">{w.projectName}</span>: need{" "}
										{formatDuration(w.hoursRemaining * 60)} in {w.daysLeft} day
										{w.daysLeft !== 1 ? "s" : ""}
									</p>
								))}
							</div>
						</div>
					)}
				</div>

				{/* Footer */}
				<div className="px-5 py-3 border-t border-border/40">
					<button
						onClick={dismiss}
						className="w-full py-2 text-sm font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
					>
						Let's go
					</button>
				</div>
			</div>
		</div>
	);
}
