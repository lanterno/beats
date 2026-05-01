/**
 * FlowByApp — third axis of the per-window grouping cards. Sits next to
 * FlowByRepo and FlowByLanguage and uses the same aggregateFlowBy helper.
 * Renders the bundle id as a friendly app name when we recognize it.
 *
 * Why a card per dimension instead of a tabbed picker: each axis answers
 * a slightly different question and they're useful at-a-glance side by
 * side. A tab would force the user to flip and lose context.
 *
 * Rows are clickable: tapping one toggles the Insights-page-wide
 * `selectedBundleId` filter that narrows the other Flow cards. Same
 * "card doesn't filter its own data" rule as FlowByRepo / FlowByLanguage,
 * so the user always has somewhere to click to switch.
 */
import { useMemo } from "react";
import { useFlowWindows } from "@/entities/session";
import { shortBundleLabel } from "@/shared/lib/bundleLabel";
import { aggregateFlowBy } from "@/shared/lib/flowAggregation";

interface Props {
	projectId?: string;
	editorRepo?: string;
	editorLanguage?: string;
	selectedBundleId?: string;
	onSelectBundleId?: (bundleId: string | undefined) => void;
}

export function FlowByApp({
	projectId,
	editorRepo,
	editorLanguage,
	selectedBundleId,
	onSelectBundleId,
}: Props = {}) {
	// Same rule as FlowByRepo / FlowByLanguage: this card does NOT filter
	// its own data by selectedBundleId — it has to keep showing every app
	// so the user has a target to click.
	const filter =
		projectId || editorRepo || editorLanguage
			? { projectId, editorRepo, editorLanguage }
			: undefined;
	const { data: windows } = useFlowWindows(undefined, undefined, filter);
	const stats = useMemo(
		() => aggregateFlowBy(windows ?? [], (w) => w.dominant_bundle_id, 5),
		[windows],
	);

	if (stats.length === 0) return null;
	const peakAvg = Math.max(...stats.map((s) => s.avg));

	const handleClick = (bundleId: string) => {
		if (!onSelectBundleId) return;
		onSelectBundleId(selectedBundleId === bundleId ? undefined : bundleId);
	};

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow by app</p>
				<p className="text-[11px] text-muted-foreground">
					today · {stats.length} {stats.length === 1 ? "app" : "apps"}
				</p>
			</div>

			<div className="space-y-1">
				{stats.map((s) => {
					const active = selectedBundleId === s.key;
					return (
						<button
							type="button"
							key={s.key}
							onClick={() => handleClick(s.key)}
							className={`w-full flex items-center gap-3 rounded-md px-1.5 py-1 transition-colors ${
								active ? "bg-accent/15" : "hover:bg-secondary/40"
							}`}
							aria-pressed={active}
						>
							<div
								className="text-foreground/80 truncate text-xs flex-1 min-w-0 text-left"
								title={s.key}
							>
								{shortBundleLabel(s.key)}
							</div>
							<div className="flex-[2] h-1.5 rounded-full bg-secondary/60 relative overflow-hidden">
								<div
									className="absolute inset-y-0 left-0 bg-accent"
									style={{ width: `${(s.avg * 100).toFixed(1)}%` }}
								/>
							</div>
							<div className="text-[11px] tabular-nums text-foreground w-9 text-right">
								{Math.round(s.avg * 100)}
							</div>
							<div className="text-[10px] tabular-nums text-muted-foreground w-12 text-right">
								{s.minutes}m
							</div>
						</button>
					);
				})}
			</div>

			{stats.length >= 2 && (
				<p className="text-[10px] text-muted-foreground border-t border-border/40 pt-2">
					Best flow today in{" "}
					<span className="text-foreground">
						{shortBundleLabel(stats.find((s) => s.avg === peakAvg)?.key ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</div>
	);
}
