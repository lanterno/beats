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
import { aggregateFlowBy, cn, shortBundleLabel } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { FOOTNOTE, LABEL, META, ROW } from "./styles";

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
		<Panel padding="px-6 py-[22px]" className="space-y-3">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<p className={LABEL}>Flow by app</p>
				<p className={META}>
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
							className={cn(
								ROW,
								"w-full flex items-center gap-3 px-2 py-1.5",
								active ? "bg-sidebar-accent" : "hover:bg-secondary",
							)}
							aria-pressed={active}
						>
							<div
								className="text-foreground font-medium truncate text-xs flex-1 min-w-0 text-left"
								title={s.key}
							>
								{shortBundleLabel(s.key)}
							</div>
							<div className="flex-[2] h-1.5 rounded-full bg-muted relative overflow-hidden">
								<div
									className="absolute inset-y-0 left-0 rounded-full bg-success/70"
									style={{ width: `${(s.avg * 100).toFixed(1)}%` }}
								/>
							</div>
							<div className="text-xs font-bold font-mono tabular-nums text-foreground w-9 text-right">
								{Math.round(s.avg * 100)}
							</div>
							<div className="text-[11px] font-medium tabular-nums text-muted-foreground w-12 text-right">
								{s.minutes}m
							</div>
						</button>
					);
				})}
			</div>

			{stats.length >= 2 && (
				<p className={FOOTNOTE}>
					Best flow today in{" "}
					<span className="text-foreground font-bold">
						{shortBundleLabel(stats.find((s) => s.avg === peakAvg)?.key ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</Panel>
	);
}
