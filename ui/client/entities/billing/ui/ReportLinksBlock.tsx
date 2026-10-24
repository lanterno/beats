/**
 * ReportLinksBlock — the owner's side of report links (docs/billing.md,
 * phase 1c): the links a client already has, and the way to make another.
 *
 * A link is a URL a client opens with no login, over a range frozen when it
 * was minted. The API returns only the token; the URL is built here from
 * the SPA's own origin, because the API does not know where the app is
 * served from. Each row says in words what that link shows, so "what can my
 * client see" is answered by reading the list rather than by opening one.
 *
 * Nothing here is gated by `withPastConsent`: a link changes no figure, it
 * only shows figures that are already there.
 */

import { Check, ChevronRight, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { describeError } from "@/shared/api";
import { cn, formatDateShort, parseIsoDate } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { useCreateReportLink, useDeleteReportLink, useReportLinks } from "../api";
import type { ReportLink } from "../model";

export interface ReportLinksBlockProps {
	clientId: string;
	/** The client's name, for the labels a screen reader reads. */
	clientName: string;
	/** The open month's first and last day: what "Share this month" covers. */
	first: string;
	last: string;
	/** The zone the link's days are bucketed in — the browser's, as everywhere. */
	tz: string;
	/** "October". */
	monthName: string;
	/** False on an archived client, which offers no writes. */
	writable?: boolean;
}

const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";
const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** The URL a client opens. The SPA's origin, since the API has no idea of it. */
export function reportUrl(token: string): string {
	return `${window.location.origin}/r/${token}`;
}

function shortDay(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? formatDateShort(d) : iso;
}

/** "Oct 1 – Oct 31", or the one day. */
function range(first: string, last: string): string {
	return first === last ? shortDay(first) : `${shortDay(first)} – ${shortDay(last)}`;
}

/** What a link shows, in the words the "can see" list is made of. */
export function describeReportLink(link: ReportLink): string {
	const parts = [
		link.showAmounts ? "hours and amounts" : "hours only",
		link.showEntries ? "with each entry" : "totals only",
	];
	return parts.join(", ");
}

function LinkRow({
	link,
	clientName,
	onRevoke,
	pending,
}: {
	link: ReportLink;
	clientName: string;
	onRevoke: () => void;
	pending: boolean;
}) {
	const [copied, setCopied] = useState(false);
	const handleCopy = async () => {
		try {
			await navigator.clipboard.writeText(reportUrl(link.token));
			setCopied(true);
			// Long enough to read, short enough that the next copy says so again.
			setTimeout(() => setCopied(false), 2000);
		} catch {
			// A browser that refuses the clipboard — no permission, or an
			// insecure origin — must not leave the user with nothing.
			toast.error("Couldn't copy. Select the link and copy it by hand.");
		}
	};

	return (
		<li className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 items-center py-2 border-t border-border first:border-t-0 text-[12.5px]">
			<span className="min-w-0">
				<span className="font-mono font-bold text-foreground whitespace-nowrap">
					{range(link.first, link.last)}
				</span>
				<span className="block text-muted-foreground font-medium truncate">
					{describeReportLink(link)}
				</span>
			</span>
			<span className="flex items-center gap-2.5">
				<button
					type="button"
					onClick={handleCopy}
					aria-label={`Copy ${clientName}'s link for ${range(link.first, link.last)}`}
					className={cn(LINKISH, "inline-flex items-center gap-1")}
				>
					{copied ? (
						<Check className="w-3 h-3" aria-hidden="true" />
					) : (
						<Copy className="w-3 h-3" aria-hidden="true" />
					)}
					{copied ? "Copied" : "Copy"}
				</button>
				<button
					type="button"
					onClick={onRevoke}
					disabled={pending}
					aria-label={`Revoke ${clientName}'s link for ${range(link.first, link.last)}`}
					className={cn(LINKISH, "text-destructive-ink")}
				>
					Revoke
				</button>
			</span>
		</li>
	);
}

export function ReportLinksBlock({
	clientId,
	clientName,
	first,
	last,
	tz,
	monthName,
	writable = true,
}: ReportLinksBlockProps) {
	// Closed until asked for, and only then read. The Clients page draws a
	// panel per client, and a list fetched for each on load would be one
	// request per client for something most months nobody opens.
	const [open, setOpen] = useState(false);
	const { data: links, isError } = useReportLinks(clientId, { enabled: open });
	const create = useCreateReportLink();
	const remove = useDeleteReportLink();
	const [composing, setComposing] = useState(false);
	const [showAmounts, setShowAmounts] = useState(true);
	const [showEntries, setShowEntries] = useState(true);

	const handleCreate = () =>
		create.mutate(
			{ clientId, input: { first, last, tz, showAmounts, showEntries } },
			{
				onSuccess: async (link) => {
					setComposing(false);
					try {
						await navigator.clipboard.writeText(reportUrl(link.token));
						toast.success("Link created and copied");
					} catch {
						toast.success("Link created. Use Copy to put it on the clipboard.");
					}
				},
				onError: (err) => toast.error(describeError(err, "Failed to create the link")),
			},
		);

	const handleRevoke = (link: ReportLink) =>
		remove.mutate(
			{ clientId, linkId: link.id },
			{
				onSuccess: () => toast.success("Link revoked"),
				onError: (err) => toast.error(describeError(err, "Failed to revoke the link")),
			},
		);

	const checkbox = (
		id: string,
		checked: boolean,
		onChange: (next: boolean) => void,
		text: string,
	) => (
		<label htmlFor={id} className="inline-flex items-center gap-1.5 text-[12.5px] font-medium">
			<input
				id={id}
				type="checkbox"
				checked={checked}
				onChange={(event) => onChange(event.target.checked)}
				className="w-3.5 h-3.5 rounded accent-accent"
			/>
			{text}
		</label>
	);

	const list = isError ? (
		// An older API during a deploy: say so, and leave the rest of the
		// panel alone, as the budgets block does.
		<p className="mt-1 text-[12.5px] text-muted-foreground font-medium">
			Shared reports aren't available right now.
		</p>
	) : links === undefined ? null : links.length === 0 ? (
		<p className="mt-1 text-[12.5px] text-muted-foreground font-medium">
			{clientName} has no link yet. A link shows only this client's projects, and needs no login.
		</p>
	) : (
		<ul className="mt-1 flex flex-col">
			{links.map((link) => (
				<LinkRow
					key={link.id}
					link={link}
					clientName={clientName}
					onRevoke={() => handleRevoke(link)}
					pending={remove.isPending}
				/>
			))}
		</ul>
	);

	return (
		<section aria-label={`${clientName}'s shared reports`} className="mt-3">
			<button
				type="button"
				aria-expanded={open}
				onClick={() => setOpen((wasOpen) => !wasOpen)}
				className={cn(
					LABEL,
					"inline-flex items-center gap-1 rounded-full hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
				)}
			>
				<ChevronRight
					className={cn("w-3 h-3 transition-transform", open && "rotate-90")}
					aria-hidden="true"
				/>
				Shared reports
			</button>
			{!open ? null : (
				<>
					{list}

					{writable &&
						!isError &&
						(composing ? (
							<div className="mt-2.5 rounded-2xl bg-secondary px-3 py-2.5">
								<p className="text-[12.5px] font-medium text-foreground">
									A link for {monthName}, {range(first, last)}:
								</p>
								<div className="mt-1.5 flex items-center gap-4 flex-wrap">
									{checkbox(
										`${clientId}-amounts`,
										showAmounts,
										setShowAmounts,
										"Show rates and amounts",
									)}
									{checkbox(`${clientId}-entries`, showEntries, setShowEntries, "Show each entry")}
								</div>
								<div className="mt-2.5 flex items-center gap-2">
									<Button
										type="button"
										size="sm"
										className="h-7 px-2.5 text-xs"
										disabled={create.isPending}
										onClick={handleCreate}
									>
										Create link
									</Button>
									<Button
										type="button"
										variant="ghost"
										size="sm"
										className="h-7 px-2.5 text-xs"
										onClick={() => setComposing(false)}
									>
										Cancel
									</Button>
								</div>
							</div>
						) : (
							<button
								type="button"
								onClick={() => setComposing(true)}
								className={cn(LINKISH, (links?.length ?? 0) > 0 && "mt-1.5")}
							>
								Share {monthName}
							</button>
						))}
				</>
			)}
		</section>
	);
}
