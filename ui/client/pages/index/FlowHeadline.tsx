/**
 * FlowHeadline — single-line flow card for the home page.
 *
 * Prefers today's slice; when today is empty (early morning, just
 * opening the laptop) it falls back to yesterday's slice so the user
 * still has some flow context. Hides only when both are empty —
 * matches the original "don't render an unhelpful empty card" rule
 * but covers the wider window where the user opens the app before
 * any new data has accrued.
 *
 * Hits /api/signals/flow-windows/summary in both cases so it's still
 * a single round-trip per slice. TanStack Query dedupes identical
 * keys, so the yesterday call is cached across the home + future
 * Insights uses.
 */
import { Link, useNavigate } from "react-router-dom";
import { useFlowWindowsSummary } from "@/entities/session";

interface YesterdayRange {
	start: string;
	end: string;
}

function yesterdayRange(now: Date = new Date()): YesterdayRange {
	const dayMs = 24 * 60 * 60 * 1000;
	const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
	const yesterdayStart = new Date(todayStart.getTime() - dayMs);
	return {
		start: yesterdayStart.toISOString(),
		end: todayStart.toISOString(),
	};
}

export function FlowHeadline() {
	const { data: today, isLoading: todayLoading } = useFlowWindowsSummary();
	const { start: yStart, end: yEnd } = yesterdayRange();
	const { data: yesterday, isLoading: yesterdayLoading } = useFlowWindowsSummary(yStart, yEnd);
	const navigate = useNavigate();

	if (todayLoading || yesterdayLoading) return null;

	// Pick the source: today when populated, otherwise yesterday. Both
	// empty → render nothing (matches the original behavior).
	const isToday = !!today && today.count > 0;
	const data = isToday ? today : yesterday;
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
				<p className="font-heading text-sm text-foreground">
					{isToday ? "Flow today" : "Flow yesterday"}
				</p>
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
							best on{" "}
							<DeepLinkSpan
								label={shortTail(data.top_repo.key)}
								title={`View Insights filtered to ${data.top_repo.key}`}
								onClick={() => navigate(`/insights?repo=${encodeURIComponent(data.top_repo!.key)}`)}
							/>
						</span>
					)}
					{data.top_language && (
						<span>
							in{" "}
							<DeepLinkSpan
								label={data.top_language.key}
								title={`View Insights filtered to ${data.top_language.key}`}
								onClick={() =>
									navigate(`/insights?language=${encodeURIComponent(data.top_language!.key)}`)
								}
							/>
						</span>
					)}
				</div>
			)}
		</Link>
	);
}

/** Pill that deep-links to a filtered Insights view from inside a
 * larger Link (the FlowHeadline card itself). Uses a plain button
 * with stopPropagation / preventDefault so we don't end up with
 * nested anchors (invalid HTML) — and so clicking the pill doesn't
 * also trigger the card's own navigation to unfiltered Insights. */
function DeepLinkSpan({
	label,
	title,
	onClick,
}: {
	label: string;
	title: string;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			title={title}
			onClick={(e) => {
				e.preventDefault();
				e.stopPropagation();
				onClick();
			}}
			className="text-foreground/80 hover:text-accent hover:underline transition-colors"
		>
			{label}
		</button>
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
