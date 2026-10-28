/**
 * Section — a named region whose heading sits *inside* its panel, above the
 * hairline, with the section's own action at the top rather than at the
 * bottom of its list. The heading used to float on the sky, which is the
 * least readable surface the app has; the region name and the heading's
 * text are unchanged, so what the tests and the E2E specs find is the same.
 */

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { HEADING_ICON, LEAD, LINKISH, PANEL_HEADING } from "./styles";

export interface SectionProps {
	/** The region's accessible name, and by default the heading's words. */
	label: string;
	/** The heading, when it reads differently from the region's name. */
	title?: ReactNode;
	icon?: LucideIcon;
	/** The section's one action, at the top right of its panel. */
	action?: ReactNode;
	/** A sentence under the heading saying what the section is for. */
	lead?: ReactNode;
	/** The body's padding; the heading keeps its own. */
	bodyClassName?: string;
	className?: string;
	children: ReactNode;
}

export function Section({
	label,
	title,
	icon: Icon,
	action,
	lead,
	bodyClassName = "px-5 py-1",
	className,
	children,
}: SectionProps) {
	return (
		<section aria-label={label} className={cn("mb-4", className)}>
			<Panel padding="p-0">
				<div className="flex items-center gap-2 flex-wrap px-5 pt-4 pb-3 border-b border-border">
					<h2 className={PANEL_HEADING}>
						{Icon && <Icon className={HEADING_ICON} aria-hidden="true" />}
						{title ?? label}
					</h2>
					{action && <div className="ml-auto flex items-center gap-2">{action}</div>}
					{lead && <p className={cn(LEAD, "basis-full")}>{lead}</p>}
				</div>
				<div className={bodyClassName}>{children}</div>
			</Panel>
		</section>
	);
}

/**
 * QueryBody — the one way a section's list reads its query: the failure in
 * the API's words with the read offered again, the loading line, the empty
 * line, else the rows. It existed as a copied ternary in seven sections,
 * none of which offered a retry.
 */
export function QueryBody<T>({
	query,
	errorText,
	empty,
	isEmpty = (data) => Array.isArray(data) && data.length === 0,
	children,
}: {
	query: {
		data: T | undefined;
		error: unknown;
		refetch: () => unknown;
		isFetching: boolean;
	};
	/** What a failure is called here, before the API's own words. */
	errorText: string;
	/** The line shown when `isEmpty` reads the data as nothing. */
	empty: ReactNode;
	isEmpty?: (data: T) => boolean;
	children: (data: T) => ReactNode;
}) {
	if (query.error) {
		return (
			<p className={`${LEAD} py-3`} role="alert">
				{describeError(query.error, errorText)}{" "}
				<button
					type="button"
					onClick={() => void query.refetch()}
					disabled={query.isFetching}
					className={LINKISH}
				>
					{query.isFetching ? "Trying…" : "Try again"}
				</button>
			</p>
		);
	}
	if (query.data === undefined) return <p className={`${LEAD} py-3`}>Loading…</p>;
	if (isEmpty(query.data)) return <p className={`${LEAD} py-3`}>{empty}</p>;
	return <>{children(query.data)}</>;
}
