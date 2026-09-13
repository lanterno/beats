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
import { useNavigate } from "react-router";
import { type InboxItem, useDismissInboxItem, useInbox } from "@/entities/intelligence";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";

const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";

const ICONS: Record<string, ReactNode> = {
	pattern: <Sparkles className="w-4 h-4" />,
	suggestion: <Lightbulb className="w-4 h-4" />,
	project_health: <AlertTriangle className="w-4 h-4" />,
};

// Severity is carried by the icon's ink — persimmon only where something is
// wrong — and the items are rows on hairlines, not boxes.
const SEVERITY_STYLES: Record<string, string> = {
	high: "text-destructive",
	medium: "text-foreground",
	low: "text-muted-foreground",
};

export function Inbox() {
	const { data, isLoading } = useInbox();
	const dismissItem = useDismissInboxItem();
	const navigate = useNavigate();

	const visible: InboxItem[] = data?.items ?? [];

	if (isLoading) return null;
	if (visible.length === 0) return null;

	return (
		<section aria-label="Inbox">
			<Panel className="h-full">
				<header className="flex items-center gap-2 mb-2">
					<InboxIcon className="w-3.5 h-3.5 text-muted-foreground" />
					<h2 className={LABEL}>Inbox</h2>
					<span className="ml-auto text-xs font-medium text-muted-foreground">
						{visible.length} {visible.length === 1 ? "item" : "items"}
					</span>
				</header>

				<ul className="flex flex-col">
					{visible.map((item: InboxItem) => (
						<li
							key={item.id}
							className="group relative border-t border-border first:border-t-0 py-2.5 text-sm"
						>
							<div className="flex items-start gap-2.5">
								<span
									className={cn(
										"mt-0.5 shrink-0",
										SEVERITY_STYLES[item.severity] ?? SEVERITY_STYLES.low,
									)}
								>
									{ICONS[item.kind] ?? <Sparkles className="w-4 h-4" />}
								</span>
								<div className="flex-1 min-w-0">
									<div className="font-bold text-foreground">{item.title}</div>
									<div className="text-muted-foreground text-[13px] mt-0.5">{item.body}</div>
									{item.cta_label && item.cta_href ? (
										<button
											type="button"
											onClick={() => navigate(item.cta_href as string)}
											className="mt-1.5 text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
										>
											{item.cta_label} →
										</button>
									) : null}
								</div>
								<button
									type="button"
									aria-label={`Dismiss ${item.title}`}
									onClick={() => dismissItem.mutate(item.id)}
									className="shrink-0 grid place-items-center w-6 h-6 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground opacity-60 group-hover:opacity-100 focus-visible:opacity-100 transition focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
								>
									<X className="w-3.5 h-3.5" />
								</button>
							</div>
						</li>
					))}
				</ul>
			</Panel>
		</section>
	);
}
