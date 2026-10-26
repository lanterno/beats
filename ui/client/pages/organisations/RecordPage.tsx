/**
 * RecordPage — one component for two routes, parameterised by the read:
 * `/organisations/:id/record` is what the organisation sees in a month
 * (`useOrgRecord`, its readers; a manager their teams, which the page
 * says), and `/organisations/:id/visible` is the same read narrowed to the
 * caller (`useVisible`, everyone) — the "what Acme can see" page shows the
 * data actually held, not a description of it. Per project, per member:
 * the shared-since date, the month's hours, a contract's balance with the
 * four terms that make it, the entries and the absences. The month is the
 * URL's `?month=` in a page bar on a card (the Clients page's idiom), and
 * on the current month the page says that a running timer is in no figure.
 *
 * A month with no entries still shows the projects and who is on them —
 * the balance is today's, not the month's, and hiding it with the empty
 * month made it look like part of the month.
 */

import type { UseQueryResult } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Download, Eye, ScrollText } from "lucide-react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";
import { monthOf, monthTitle, nextMonth, prevMonth, useOpenMonth } from "@/entities/billing";
import type { MemberBalance, MemberRecord, OrgRecord } from "@/entities/organisation";
import {
	complianceCsvUrl,
	describeShareFrom,
	recordCsvUrl,
	useMembership,
	visibleCsvUrl,
} from "@/entities/organisation";
import { ApiError, describeError } from "@/shared/api";
import {
	cn,
	downloadFile,
	formatDate,
	formatDateOnly,
	hoursText,
	todayIso as readToday,
} from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { AbsenceList } from "./AbsenceList";
import { EntriesTable } from "./EntriesTable";
import { KIND_LABELS } from "./kinds";
import { CRUMB, LEAD, MONTH_NAV, PAGE, PAGE_TITLE, PAGEBAR } from "./styles";

export interface RecordPageProps {
	variant: "record" | "visible";
	useRecord: (organisationId: string, month: string) => UseQueryResult<OrgRecord>;
}

/** A day the API sends bare, or an instant: either way the reader's own words. */
function dayText(value: string): string {
	return /^\d{4}-\d{2}-\d{2}$/.test(value) ? formatDateOnly(value) : formatDate(value);
}

/** "+4.5 h ahead" or "−2 h behind" — of what the contract expected. */
function balanceText(balance: number): string {
	const rounded = Number(balance.toFixed(2));
	if (rounded === 0) return "even";
	return rounded > 0 ? `+${hoursText(rounded)} ahead` : `−${hoursText(-rounded)} behind`;
}

/** The four terms a balance is made of, each signed as it entered. */
function balanceTerms(balance: MemberBalance): string {
	const signed = (v: number) =>
		Number(v.toFixed(2)) < 0 ? `−${hoursText(-v)}` : `+${hoursText(v)}`;
	return [
		`opening ${signed(balance.opening)}`,
		`worked ${hoursText(balance.worked)}`,
		`expected ${hoursText(balance.expectedThrough)}`,
		`adjusted ${signed(balance.adjusted)}`,
	].join(" · ");
}

function MemberBlock({ member, project }: { member: MemberRecord; project: string }) {
	const quiet = member.entries.length === 0 && member.absences.length === 0;
	return (
		<section aria-label={member.name} className="space-y-2">
			<div className="flex items-baseline gap-2 flex-wrap text-[12.5px]">
				<h3 className="font-heading text-[13px] font-extrabold text-foreground">{member.name}</h3>
				<span className="text-muted-foreground">shared {describeShareFrom(member.sharedFrom)}</span>
				{!member.active && <span className="text-muted-foreground">· no longer assigned</span>}
				<span className="ml-auto font-mono font-bold text-foreground">
					{hoursText(member.hours)}
					<span className="font-body font-medium text-muted-foreground"> this month</span>
				</span>
			</div>
			{member.balance ? (
				// Today's balance, whatever month is open — it is not a figure of
				// the month, which is why it says "today" and when, and shows the
				// four terms it is made of rather than a bare number.
				<p className="text-[12.5px] text-foreground font-medium">
					Balance today: {balanceText(member.balance.balance)}{" "}
					<span className="text-muted-foreground">
						({balanceTerms(member.balance)} — as of {dayText(member.balance.asOf)})
					</span>
				</p>
			) : (
				member.hasContract && (
					// A balance sums every hour since the contract began; on a
					// connected project with hours before the shared-from day,
					// the API withholds it rather than carry what was kept back.
					<p className={LEAD}>
						Balance not shared: the contract reaches back before the hours shared with the
						organisation.
					</p>
				)
			)}
			{member.totals.entries > 0 && (
				<p className={LEAD}>
					All time: {hoursText(member.totals.hours)} across {member.totals.entries}{" "}
					{member.totals.entries === 1 ? "entry" : "entries"}
					{member.totals.first && <> since {dayText(member.totals.first)}</>}.
				</p>
			)}
			{quiet ? (
				<p className={LEAD}>Nothing this month.</p>
			) : (
				<>
					{member.entries.length > 0 && (
						<EntriesTable
							entries={member.entries}
							label={`Entries on ${project} for ${member.name}`}
						/>
					)}
					<AbsenceList absences={member.absences} label={`Absences of ${member.name}`} />
				</>
			)}
		</section>
	);
}

export function RecordPage({ variant, useRecord }: RecordPageProps) {
	const { id = "" } = useParams<{ id: string }>();
	const today = readToday();
	const [month, setMonth] = useOpenMonth(today);
	const current = month === monthOf(today);
	const query = useRecord(id, month);
	// The record is a reader's page, but whose slice it shows depends on the
	// role: a manager's is narrowed to their teams, and the page says so.
	const membership = useMembership(id);
	const record = query.data;
	const name = record?.organisation.name ?? "";
	const title = variant === "visible" ? `What ${name} sees` : `${name}'s record`;
	// What to call the page before the organisation has a name: the read may
	// fail, and a heading stuck on "Loading…" over an error panel is a lie.
	const pageTitle = variant === "visible" ? "What they see" : "The record";
	const entriesInMonth = (record?.projects ?? []).some((p) =>
		p.members.some((m) => m.entries.length > 0 || m.absences.length > 0),
	);
	const monthHours = (record?.projects ?? []).reduce(
		(sum, p) => sum + p.members.reduce((h, m) => h + m.hours, 0),
		0,
	);

	const download = async (url: string, filename: string) => {
		try {
			await downloadFile(url, filename);
			toast.success("Downloaded");
		} catch (err) {
			toast.error(describeError(err, "The download failed."));
		}
	};

	let body: React.ReactNode;
	if (query.error) {
		const forbidden = query.error instanceof ApiError && query.error.statusCode === 403;
		body = (
			<Panel role="alert" padding="px-6 py-[22px]">
				<p className="font-heading text-lg font-extrabold text-foreground">
					{!forbidden
						? "The record could not be read."
						: variant === "record"
							? "Owners, admins, managers and viewers only."
							: "This organisation can see nothing of yours right now."}
				</p>
				{!forbidden && (
					<p className="mt-1 text-xs text-muted-foreground">
						{describeError(query.error, "Nothing came back.")}
					</p>
				)}
			</Panel>
		);
	} else if (!record) {
		body = (
			<Panel padding="px-6 py-[22px]">
				<p className={LEAD}>Loading…</p>
			</Panel>
		);
	} else {
		body = (
			<>
				{!entriesInMonth && (
					<Panel padding="px-6 py-[22px]">
						<p className="font-heading text-lg font-extrabold text-foreground">
							No entries in {monthTitle(month)}.
						</p>
						<p className={cn(LEAD, "mt-1")}>
							The projects and balances below are not the month's: a balance is today's.
						</p>
					</Panel>
				)}
				{record.projects.map(({ project, members }) => (
					<Panel
						key={project.id}
						role="region"
						aria-label={project.name}
						padding="px-6 py-5"
						className="space-y-4"
					>
						<div className="flex items-center gap-2">
							<span
								className="w-2.5 h-2.5 rounded-full shrink-0"
								style={{ backgroundColor: project.color ?? "var(--color-muted-foreground)" }}
								aria-hidden="true"
							/>
							<h2 className="font-heading text-[15px] font-extrabold text-foreground">
								{project.name}
							</h2>
							<span className="text-[12.5px] text-muted-foreground">
								{KIND_LABELS[project.kind]}
							</span>
							<span className="ml-auto font-mono text-[13px] font-bold text-foreground">
								{hoursText(members.reduce((h, m) => h + m.hours, 0))}
							</span>
						</div>
						{members.length === 0 ? (
							<p className={LEAD}>Nobody is on it.</p>
						) : (
							<div className="divide-y divide-border [&>*]:py-3 [&>*:first-child]:pt-0 [&>*:last-child]:pb-0">
								{members.map((member) => (
									<MemberBlock key={member.userId} member={member} project={project.name} />
								))}
							</div>
						)}
					</Panel>
				))}
			</>
		);
	}

	return (
		<div className={PAGE}>
			<Panel padding="px-5 py-3" className={PAGEBAR}>
				{variant === "visible" ? (
					<Eye className="w-5 h-5 text-muted-foreground shrink-0" aria-hidden="true" />
				) : (
					<ScrollText className="w-5 h-5 text-muted-foreground shrink-0" aria-hidden="true" />
				)}
				<div className="min-w-0">
					<Link to={`/organisations/${id}`} className={CRUMB}>
						{name || "Organisation"}
					</Link>
					<h1 className={cn(PAGE_TITLE, "truncate")}>
						{record ? title : query.error ? pageTitle : `${pageTitle}…`}
					</h1>
				</div>
				<div className="inline-flex items-center gap-1">
					<button
						type="button"
						onClick={() => setMonth(prevMonth(month))}
						aria-label="Previous month"
						className={MONTH_NAV}
					>
						<ChevronLeft className="w-4 h-4" aria-hidden="true" />
					</button>
					<h2
						className="px-1 font-heading text-[15px] font-extrabold text-foreground whitespace-nowrap"
						aria-live="polite"
					>
						{monthTitle(month)}
						{current && (
							<span className="font-body font-medium text-muted-foreground"> · so far</span>
						)}
					</h2>
					<button
						type="button"
						onClick={() => setMonth(nextMonth(month))}
						disabled={current}
						aria-label="Next month"
						className={MONTH_NAV}
					>
						<ChevronRight className="w-4 h-4" aria-hidden="true" />
					</button>
				</div>
				{!current && (
					<button
						type="button"
						onClick={() => setMonth(monthOf(today))}
						className="text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full bg-secondary px-3 py-1.5 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
					>
						This month
					</button>
				)}
				{record && (
					<span className="font-mono text-[13px] font-bold text-foreground whitespace-nowrap">
						{hoursText(monthHours)}
						<span className="font-body font-medium text-muted-foreground"> this month</span>
					</span>
				)}
				{variant === "visible" && record && (
					<Button
						type="button"
						variant="secondary"
						size="sm"
						className="ml-auto"
						onClick={() => void download(visibleCsvUrl(id, month), `${name}-visible-${month}.csv`)}
					>
						<Download aria-hidden="true" />
						This month as CSV
					</Button>
				)}
				{variant === "record" && record && (
					<span className="ml-auto flex items-center gap-2">
						<Button
							type="button"
							variant="secondary"
							size="sm"
							onClick={() => void download(recordCsvUrl(id, month), `${name}-record-${month}.csv`)}
						>
							<Download aria-hidden="true" />
							Record CSV
						</Button>
						<Button
							type="button"
							variant="secondary"
							size="sm"
							title="Per member and day: first start, last end, breaks and the total"
							onClick={() =>
								void download(complianceCsvUrl(id, month), `${name}-compliance-${month}.csv`)
							}
						>
							<Download aria-hidden="true" />
							Compliance CSV
						</Button>
					</span>
				)}
			</Panel>

			{(variant === "visible" || membership.data?.role === "manager" || current) && record && (
				<Panel padding="px-5 py-3" className="space-y-1">
					{variant === "visible" && (
						<p className="text-[13px] font-medium text-foreground">
							This is the data {name} holds about you, read through the same query it uses.
						</p>
					)}
					{variant === "record" && membership.data?.role === "manager" && (
						<p className="text-[13px] font-medium text-foreground">
							As a manager you read your teams: members outside them are not in these figures.
						</p>
					)}
					{current && (
						<p className={LEAD}>
							Nothing about now crosses: a timer still running is in no figure here until it stops.
						</p>
					)}
				</Panel>
			)}

			{body}
		</div>
	);
}
