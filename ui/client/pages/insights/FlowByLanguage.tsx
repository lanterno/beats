/**
 * FlowByLanguage — sibling to FlowByRepo. Groups today's flow windows by
 * the language id reported by the editor extension and shows where the
 * user flows best by language. Reuses the shared useFlowWindows() hook so
 * it costs no extra API call.
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

export function FlowByLanguage({
	projectId,
	editorRepo,
}: {
	projectId?: string;
	editorRepo?: string;
} = {}) {
	const filter = projectId || editorRepo ? { projectId, editorRepo } : undefined;
	const { data: windows } = useFlowWindows(undefined, undefined, filter);
	const stats = useMemo(
		() => aggregateFlowBy(windows ?? [], (w) => w.editor_language, 5),
		[windows],
	);

	if (stats.length === 0) return null;
	const peakAvg = Math.max(...stats.map((s) => s.avg));

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow by language</p>
				<p className="text-[11px] text-muted-foreground">
					today · {stats.length} {stats.length === 1 ? "language" : "languages"}
				</p>
			</div>

			<div className="space-y-2">
				{stats.map((s) => (
					<div key={s.key} className="flex items-center gap-3">
						<div className="text-foreground/80 truncate text-xs flex-1 min-w-0">
							{LANGUAGE_LABELS[s.key] ?? s.key}
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
					</div>
				))}
			</div>

			{stats.length >= 2 && (
				<p className="text-[10px] text-muted-foreground border-t border-border/40 pt-2">
					Best flow today in{" "}
					<span className="text-foreground">
						{(() => {
							const best = stats.find((s) => s.avg === peakAvg)?.key ?? "";
							return LANGUAGE_LABELS[best] ?? best;
						})()}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</div>
	);
}
