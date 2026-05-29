/**
 * Inbox — unified dashboard card surfacing intelligence outputs.
 *
 * Aggregates patterns, daily suggestions, and project-health alerts from
 * `GET /api/intelligence/inbox`. Dismissals for all three kinds persist
 * server-side (`POST /api/intelligence/inbox/{id}/dismiss`), so a dismissed
 * item stays gone across reloads and devices — the optimistic cache update
 * hides it instantly.
 */

import { AlertTriangle, Inbox as InboxIcon, Lightbulb, Sparkles, X } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { type InboxItem, useDismissInboxItem, useInbox } from "@/entities/intelligence";
import { cn } from "@/shared/lib";

const ICONS: Record<string, ReactNode> = {
	pattern: <Sparkles className="w-4 h-4" />,
	suggestion: <Lightbulb className="w-4 h-4" />,
	project_health: <AlertTriangle className="w-4 h-4" />,
};

const SEVERITY_STYLES: Record<string, string> = {
	high: "border-red-500/40 bg-red-500/5",
	medium: "border-amber-500/40 bg-amber-500/5",
	low: "border-border/60 bg-card",
};

export function Inbox() {
	const { data, isLoading } = useInbox();
	const dismissItem = useDismissInboxItem();
	const navigate = useNavigate();

	const visible: InboxItem[] = data?.items ?? [];

	if (isLoading) return null;
	if (visible.length === 0) return null;

	return (
		<section
			aria-label="Inbox"
			className="rounded-xl border border-border/60 bg-card p-4 shadow-card"
		>
			<header className="flex items-center gap-2 mb-3">
				<InboxIcon className="w-4 h-4 text-muted-foreground" />
				<h2 className="text-sm font-semibold text-foreground">Inbox</h2>
				<span className="ml-auto text-[11px] text-muted-foreground/70">
					{visible.length} {visible.length === 1 ? "item" : "items"}
				</span>
			</header>

			<ul className="space-y-2">
				{visible.map((item: InboxItem) => (
					<li
						key={item.id}
						className={cn(
							"group relative rounded-lg border px-3 py-2 text-sm transition-colors",
							SEVERITY_STYLES[item.severity] ?? SEVERITY_STYLES.low,
						)}
					>
						<div className="flex items-start gap-2">
							<span className="text-muted-foreground mt-0.5 shrink-0">
								{ICONS[item.kind] ?? <Sparkles className="w-4 h-4" />}
							</span>
							<div className="flex-1 min-w-0">
								<div className="font-medium text-foreground">{item.title}</div>
								<div className="text-muted-foreground text-[13px] mt-0.5">{item.body}</div>
								{item.cta_label && item.cta_href ? (
									<button
										type="button"
										onClick={() => navigate(item.cta_href as string)}
										className="mt-2 text-[12px] text-accent hover:underline"
									>
										{item.cta_label} →
									</button>
								) : null}
							</div>
							<button
								type="button"
								aria-label={`Dismiss ${item.title}`}
								onClick={() => dismissItem.mutate(item.id)}
								className="shrink-0 rounded-md p-1 text-muted-foreground/60 hover:bg-secondary/50 hover:text-foreground opacity-60 group-hover:opacity-100 transition"
							>
								<X className="w-3.5 h-3.5" />
							</button>
						</div>
					</li>
				))}
			</ul>
		</section>
	);
}
