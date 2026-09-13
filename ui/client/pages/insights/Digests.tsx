/**
 * Digests Page
 * List of weekly digest cards with expandable project breakdowns.
 */

import { ChevronDown, Plus, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";
import { useDigests, useGenerateDigest } from "@/entities/intelligence";
import type { WeeklyDigest } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { LABEL } from "./styles";

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
		<Panel padding="p-0" className="overflow-hidden">
			<button
				type="button"
				onClick={() => setExpanded(!expanded)}
				className="w-full px-6 py-4 text-left hover:bg-secondary transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
			>
				<div className="flex items-center gap-3">
					<div className="flex-1 min-w-0">
						<p className="text-sm font-bold text-foreground">{formatWeekRange(digest.week_of)}</p>
						<p className="text-xs font-medium text-muted-foreground mt-0.5">
							{digest.total_hours.toFixed(1)}h across {digest.session_count} sessions
							{digest.top_project_name && <> — Top: {digest.top_project_name}</>}
						</p>
					</div>

					{delta !== null && delta !== undefined && (
						<div
							className={cn(
								"flex items-center gap-0.5 text-xs font-bold tabular-nums",
								delta > 0
									? "text-success-ink"
									: delta < 0
										? "text-destructive-ink"
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
								"text-xs px-2.5 py-0.5 rounded-full bg-secondary font-bold tabular-nums",
								digest.productivity_score >= 70
									? "text-success-ink"
									: digest.productivity_score >= 40
										? "text-foreground"
										: "text-destructive-ink",
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
					<p className="text-xs font-medium text-muted-foreground mt-2 italic">
						{digest.observation}
					</p>
				)}
			</button>

			{expanded && (
				<div className="px-6 pb-4 pt-1 space-y-2">
					<div className="grid grid-cols-3 gap-3 text-center text-xs">
						<div>
							<p className={LABEL}>Active days</p>
							<p className="mt-1 text-sm font-bold text-foreground">{digest.active_days}</p>
						</div>
						<div>
							<p className={LABEL}>Longest day</p>
							<p className="mt-1 text-sm font-bold text-foreground">
								{digest.longest_day ?? "—"} ({digest.longest_day_hours.toFixed(1)}h)
							</p>
						</div>
						<div>
							<p className={LABEL}>Streak</p>
							<p className="mt-1 text-sm font-bold text-foreground">{digest.best_streak} days</p>
						</div>
					</div>

					{digest.project_breakdown.length > 0 && (
						<div className="pt-2">
							{digest.project_breakdown.map((p) => (
								<div
									key={p.project_id}
									className="flex items-center gap-2 text-xs py-2 border-t border-border"
								>
									<span className="text-foreground font-medium flex-1 truncate">{p.name}</span>
									<span className="font-bold font-mono tabular-nums text-foreground">
										{p.hours.toFixed(1)}h
									</span>
								</div>
							))}
						</div>
					)}
				</div>
			)}
		</Panel>
	);
}

export default function Digests() {
	const { data: digests } = useDigests();
	const generateMutation = useGenerateDigest();

	return (
		<div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<h1 className="font-heading text-xl text-foreground">Weekly Digests</h1>
				<Button
					size="sm"
					onClick={() => generateMutation.mutate(undefined)}
					disabled={generateMutation.isPending}
					className="h-8 px-3.5 text-xs"
				>
					<Plus />
					{generateMutation.isPending ? "Generating..." : "Generate latest"}
				</Button>
			</div>

			{!digests || digests.length === 0 ? (
				<Panel
					padding="py-8 px-6"
					className="text-center text-sm font-medium text-muted-foreground"
				>
					No digests yet. Click "Generate latest" to create your first weekly summary.
				</Panel>
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
