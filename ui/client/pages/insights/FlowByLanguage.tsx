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
import { aggregateFlowBy } from "@/shared/lib/flowAggregation";

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
	selectedLanguage?: string;
	onSelectLanguage?: (lang: string | undefined) => void;
}

export function FlowByLanguage({
	projectId,
	editorRepo,
	selectedLanguage,
	onSelectLanguage,
}: Props = {}) {
	const filter = projectId || editorRepo ? { projectId, editorRepo } : undefined;
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
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow by language</p>
				<p className="text-[11px] text-muted-foreground">
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
							className={`w-full flex items-center gap-3 rounded-md px-1.5 py-1 transition-colors ${
								active ? "bg-accent/15" : "hover:bg-secondary/40"
							}`}
							aria-pressed={active}
						>
							<div
								className="text-foreground/80 truncate text-xs flex-1 min-w-0 text-left"
								title={s.key}
							>
								{labelOf(s.key)}
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
						{labelOf(stats.find((s) => s.avg === peakAvg)?.key ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</div>
	);
}
