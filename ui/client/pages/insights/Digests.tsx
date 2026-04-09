/**
 * Digests Page
 * List of weekly digest cards with expandable project breakdowns.
 */

import { ChevronDown, Plus, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";
import { useDigests, useGenerateDigest } from "@/entities/intelligence";
import type { WeeklyDigest } from "@/shared/api";
import { cn } from "@/shared/lib";

function formatWeekRange(weekOf: string): string {
	const monday = new Date(weekOf);
	const sunday = new Date(monday);
	sunday.setDate(sunday.getDate() + 6);
	const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
	return `${fmt(monday)} — ${fmt(sunday)}`;
}

function DigestCard({ digest }: { digest: WeeklyDigest }) {
	const [expanded, setExpanded] = useState(false);
	const delta = digest.vs_last_week_pct;

	return (
		<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
			<button
				onClick={() => setExpanded(!expanded)}
				className="w-full px-4 py-3 text-left hover:bg-secondary/20 transition-colors"
			>
				<div className="flex items-center gap-3">
					<div className="flex-1 min-w-0">
						<p className="text-sm font-medium text-foreground">{formatWeekRange(digest.week_of)}</p>
						<p className="text-xs text-muted-foreground mt-0.5">
							{digest.total_hours.toFixed(1)}h across {digest.session_count} sessions
							{digest.top_project_name && <> — Top: {digest.top_project_name}</>}
						</p>
					</div>

					{delta !== null && delta !== undefined && (
						<div
							className={cn(
								"flex items-center gap-0.5 text-xs font-medium tabular-nums",
								delta > 0
									? "text-accent"
									: delta < 0
										? "text-destructive"
										: "text-muted-foreground",
							)}
						>
							{delta > 0 ? (
								<TrendingUp className="w-3 h-3" />
							) : delta < 0 ? (
								<TrendingDown className="w-3 h-3" />
							) : null}
							{delta > 0 ? "+" : ""}
							{delta.toFixed(0)}%
						</div>
					)}

					<div className="flex items-center gap-2">
						<span
							className={cn(
								"text-xs px-2 py-0.5 rounded-full font-medium tabular-nums",
								digest.productivity_score >= 70
									? "bg-accent/10 text-accent"
									: digest.productivity_score >= 40
										? "bg-warning/10 text-warning"
										: "bg-destructive/10 text-destructive",
							)}
						>
							{digest.productivity_score}
						</span>
						<ChevronDown
							className={cn(
								"w-3.5 h-3.5 text-muted-foreground transition-transform",
								expanded && "rotate-180",
							)}
						/>
					</div>
				</div>

				{digest.observation && (
					<p className="text-xs text-muted-foreground/70 mt-2 italic">{digest.observation}</p>
				)}
			</button>

			{expanded && (
				<div className="border-t border-border/40 px-4 py-3 space-y-2">
					<div className="grid grid-cols-3 gap-3 text-center text-xs">
						<div>
							<p className="text-muted-foreground">Active days</p>
							<p className="font-medium text-foreground">{digest.active_days}</p>
						</div>
						<div>
							<p className="text-muted-foreground">Longest day</p>
							<p className="font-medium text-foreground">
								{digest.longest_day ?? "—"} ({digest.longest_day_hours.toFixed(1)}h)
							</p>
						</div>
						<div>
							<p className="text-muted-foreground">Streak</p>
							<p className="font-medium text-foreground">{digest.best_streak} days</p>
						</div>
					</div>

					{digest.project_breakdown.length > 0 && (
						<div className="space-y-1 pt-2">
							{(digest.project_breakdown as Array<{ name?: string; hours?: number }>).map(
								(p, i) => (
									<div key={i} className="flex items-center gap-2 text-xs">
										<span className="text-foreground flex-1 truncate">{p.name ?? "Unknown"}</span>
										<span className="tabular-nums text-muted-foreground">
											{(p.hours ?? 0).toFixed(1)}h
										</span>
									</div>
								),
							)}
						</div>
					)}
				</div>
			)}
		</div>
	);
}

export default function Digests() {
	const { data: digests } = useDigests();
	const generateMutation = useGenerateDigest();

	return (
		<div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
			<div className="flex items-center justify-between">
				<h1 className="font-heading text-xl text-foreground">Weekly Digests</h1>
				<button
					onClick={() => generateMutation.mutate(undefined)}
					disabled={generateMutation.isPending}
					className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-accent text-accent-foreground hover:bg-accent/85 disabled:opacity-50 transition-colors"
				>
					<Plus className="w-3 h-3" />
					{generateMutation.isPending ? "Generating..." : "Generate latest"}
				</button>
			</div>

			{!digests || digests.length === 0 ? (
				<div className="rounded-lg border border-dashed border-border py-8 text-center text-muted-foreground/50 text-sm">
					No digests yet. Click "Generate latest" to create your first weekly summary.
				</div>
			) : (
				<div className="space-y-3">
					{digests.map((d) => (
						<DigestCard key={d.week_of} digest={d} />
					))}
				</div>
			)}
		</div>
	);
}
