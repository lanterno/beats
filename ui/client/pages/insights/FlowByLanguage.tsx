/**
 * FlowByLanguage — sibling to FlowByRepo. Groups today's flow windows by
 * the language id reported by the editor extension and shows where the
 * user flows best by language. Reuses the shared useFlowWindows() hook so
 * it costs no extra API call.
 *
 * Rows are clickable: tapping one toggles the Insights-page-wide
 * `selectedLanguage` filter that narrows every other Flow card to that
 * language. Tapping the same row again clears it. FlowByLanguage itself
 * does NOT filter its own data — it has to keep showing all languages so
 * the user has somewhere to click to switch (same rationale as FlowByRepo).
 */
import { useMemo } from "react";
import { useFlowWindows } from "@/entities/session";
import { aggregateFlowBy, cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { FOOTNOTE, LABEL, META, ROW } from "./styles";

// Tiny mapping from VS Code language ids to nicer display labels. Anything
// not listed falls through unchanged — the language id is itself usually
// fine ("rust", "python") but a few benefit from cleanup.
const LANGUAGE_LABELS: Record<string, string> = {
	typescript: "TypeScript",
	typescriptreact: "TSX",
	javascript: "JavaScript",
	javascriptreact: "JSX",
	dart: "Dart",
	go: "Go",
	rust: "Rust",
	python: "Python",
	json: "JSON",
	jsonc: "JSON",
	yaml: "YAML",
	markdown: "Markdown",
	html: "HTML",
	css: "CSS",
	scss: "SCSS",
	plaintext: "Plain text",
	shellscript: "Shell",
};

interface Props {
	projectId?: string;
	editorRepo?: string;
	bundleId?: string;
	selectedLanguage?: string;
	onSelectLanguage?: (lang: string | undefined) => void;
}

export function FlowByLanguage({
	projectId,
	editorRepo,
	bundleId,
	selectedLanguage,
	onSelectLanguage,
}: Props = {}) {
	const filter =
		projectId || editorRepo || bundleId ? { projectId, editorRepo, bundleId } : undefined;
	const { data: windows } = useFlowWindows(undefined, undefined, filter);
	const stats = useMemo(
		() => aggregateFlowBy(windows ?? [], (w) => w.editor_language, 5),
		[windows],
	);

	if (stats.length === 0) return null;
	const peakAvg = Math.max(...stats.map((s) => s.avg));

	const handleClick = (lang: string) => {
		if (!onSelectLanguage) return;
		onSelectLanguage(selectedLanguage === lang ? undefined : lang);
	};

	const labelOf = (key: string) => LANGUAGE_LABELS[key] ?? key;

	return (
		<Panel padding="px-6 py-[22px]" className="space-y-3">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<p className={LABEL}>Flow by language</p>
				<p className={META}>
					today · {stats.length} {stats.length === 1 ? "language" : "languages"}
				</p>
			</div>

			<div className="space-y-1">
				{stats.map((s) => {
					const active = selectedLanguage === s.key;
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
								{labelOf(s.key)}
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
						{labelOf(stats.find((s) => s.avg === peakAvg)?.key ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</Panel>
	);
}
