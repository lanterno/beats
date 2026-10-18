/**
 * ReportLinksSection — a client's report links, folded under its panel
 * (docs/billing.md, phase 1c): each link's label, days, what it shows, its
 * projects, its zone and its last day or that it has ended, the client's
 * billed projects it leaves out, and what can be done with it. A live link
 * is turned off after a question, since whoever holds it loses the report;
 * an ended one is only removed from the list. Both delete it. Replacing one
 * reopens the share dialog from it, which turns it off before making the
 * new one.
 */

import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
	notOnLink,
	type ReportLink,
	ReportLinkRow,
	TURN_OFF_QUESTION,
	useDeleteReportLink,
} from "@/entities/report-link";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { useConfirm } from "@/shared/ui";

export interface ReportLinksSectionProps {
	clientName: string;
	links: readonly ReportLink[];
	/** The client's billed projects, for "Not on this link" and whether Replace has anything to cover. */
	billedProjectIds: readonly string[];
	projectNames: ReadonlyMap<string, string>;
	onPreview: (link: ReportLink) => void;
	onReplace: (link: ReportLink) => void;
}

const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";
const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

export function ReportLinksSection({
	clientName,
	links,
	billedProjectIds,
	projectNames,
	onPreview,
	onReplace,
}: ReportLinksSectionProps) {
	const [open, setOpen] = useState(false);
	const remove = useDeleteReportLink();
	const { confirm, confirmDialog } = useConfirm();

	const deleteLink = (link: ReportLink) =>
		remove.mutate(link.id, {
			onSuccess: () =>
				toast.success(link.state === "live" ? "Report link turned off" : "Report link removed"),
			onError: (err) => toast.error(describeError(err, "Failed to turn the link off")),
		});

	const turnOff = async (link: ReportLink) => {
		if (await confirm(TURN_OFF_QUESTION)) deleteLink(link);
	};

	return (
		<section aria-label={`${clientName}'s report links`} className="mt-3">
			<button
				type="button"
				aria-expanded={open}
				onClick={() => setOpen((was) => !was)}
				className={cn(
					LABEL,
					"inline-flex items-center gap-1 rounded-full hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
				)}
			>
				<ChevronRight
					className={cn("w-3 h-3 transition-transform", open && "rotate-90")}
					aria-hidden="true"
				/>
				Report links ({links.length})
			</button>
			{open && (
				<ul className="mt-1.5 flex flex-col">
					{links.map((link) => (
						<li key={link.id} className="py-2 border-t border-border">
							<ReportLinkRow
								link={link}
								leftOut={notOnLink(link, billedProjectIds, projectNames)}
								actions={
									<>
										{link.projects.length > 0 && (
											<button type="button" onClick={() => onPreview(link)} className={LINKISH}>
												Preview
											</button>
										)}
										{billedProjectIds.length > 0 && (
											<button type="button" onClick={() => onReplace(link)} className={LINKISH}>
												Replace…
											</button>
										)}
										{link.state === "live" ? (
											<button
												type="button"
												onClick={() => void turnOff(link)}
												disabled={remove.isPending}
												className={cn(LINKISH, "text-destructive-ink")}
											>
												Turn off
											</button>
										) : (
											<button
												type="button"
												onClick={() => deleteLink(link)}
												disabled={remove.isPending}
												className={cn(LINKISH, "text-destructive-ink")}
											>
												Remove
											</button>
										)}
									</>
								}
							/>
						</li>
					))}
				</ul>
			)}
			{confirmDialog}
		</section>
	);
}
