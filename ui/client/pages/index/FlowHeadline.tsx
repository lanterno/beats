/**
 * FlowHeadline — single-line "today's flow" card for the home page.
 *
 * Hits /api/signals/flow-windows/summary so it's a single round-trip
 * (no row pagination + client-side reduction). Different shape than
 * the Insights FlowToday card — this is glanceable and cheap, FlowToday
 * has the sparkline and inspector. Tapping the card jumps to /insights
 * for the deeper view.
 *
 * Hides itself with no message when there are zero windows today —
 * the home page already has plenty of cards and an empty "your flow:
 * nothing" reads as broken rather than informative. The Insights page
 * surfaces the empty-state guidance for users who actually navigate
 * to the flow surface.
 */
import { Link } from "react-router-dom";
import { useFlowWindowsSummary } from "@/entities/session";

export function FlowHeadline() {
	const { data, isLoading } = useFlowWindowsSummary();

	if (isLoading) return null;
	if (!data || data.count === 0) return null;

	const avg = Math.round(data.avg * 100);
	const peak = Math.round(data.peak * 100);
	const peakAt = data.peak_at ? formatTime(data.peak_at) : null;

	return (
		<Link
			to="/insights"
			className="block rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 hover:bg-secondary/30 transition-colors"
		>
			<div className="flex items-baseline justify-between mb-1.5">
				<p className="font-heading text-sm text-foreground">Flow today</p>
				<p className="text-[11px] text-muted-foreground">view details &rarr;</p>
			</div>

			<div className="flex items-baseline gap-4 text-[12px] text-muted-foreground tabular-nums">
				<span>
					<span className="font-heading text-2xl text-accent">{avg}</span>
					<span className="text-[10px] text-muted-foreground"> /100</span>
				</span>
				<span>
					peak <span className="text-foreground">{peak}</span>
					{peakAt && <span className="text-muted-foreground"> at {peakAt}</span>}
				</span>
				<span>
					<span className="text-foreground">{data.count}</span> windows
				</span>
			</div>

			{(data.top_repo || data.top_language || data.top_bundle) && (
				<div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground border-t border-border/40 pt-1.5">
					{data.top_repo && (
						<span>
							best on <span className="text-foreground/80">{shortTail(data.top_repo.key)}</span>
						</span>
					)}
					{data.top_language && (
						<span>
							in <span className="text-foreground/80">{data.top_language.key}</span>
						</span>
					)}
				</div>
			)}
		</Link>
	);
}

function formatTime(iso: string): string {
	const d = new Date(iso);
	return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function shortTail(path: string): string {
	const parts = path.split(/[\\/]/).filter(Boolean);
	if (parts.length <= 2) return parts.join("/") || path;
	return parts.slice(-2).join("/");
}
