/**
 * RecordPage — one component for two routes, parameterised by the read:
 * `/organisations/:id/record` is what the organisation sees in a month
 * (`useOrgRecord`, admins), and `/organisations/:id/visible` is the same
 * read narrowed to the caller (`useVisible`, everyone) — the "what Acme
 * can see" page shows the data actually held, not a description of it.
 * Per project, per member: the shared-since date, the month's hours, a
 * contract's balance, the entries and the absences. The month is the
 * URL's `?month=`, stepped with ‹ ›.
 */

import type { UseQueryResult } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Link, useParams } from "react-router";
import { monthOf, nextMonth, prevMonth } from "@/entities/billing";
import type { MemberRecord, OrgRecord } from "@/entities/organisation";
import { describeShareFrom } from "@/entities/organisation";
import { ApiError, describeError } from "@/shared/api";
import { cn, formatDate, formatDateOnly, hoursText, todayIso as readToday } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { EntriesTable } from "./EntriesTable";
import { KIND_LABELS } from "./kinds";
import { LABEL, LEAD, LINKISH, SKY_NAV, TITLE } from "./styles";
import { useOpenMonth } from "./useOpenMonth";

export interface RecordPageProps {
	variant: "record" | "visible";
	useRecord: (organisationId: string, month: string) => UseQueryResult<OrgRecord>;
}

/** "October 2026". */
function monthTitle(month: string): string {
	const date = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1, 12);
	return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

/** A day the API sends bare, or an instant: either way the reader's own words. */
function dayText(value: string): string {
	return /^\d{4}-\d{2}-\d{2}$/.test(value) ? formatDateOnly(value) : formatDate(value);
}

/** "+4.5 h over" or "−2 h owed", the contract's balance as the organisation reads it. */
export function balanceText(balance: number): string {
	const rounded = Number(balance.toFixed(2));
	if (rounded === 0) return "even";
	return rounded > 0 ? `+${hoursText(rounded)} over` : `−${hoursText(-rounded)} owed`;
}

function MemberBlock({ member, project }: { member: MemberRecord; project: string }) {
	const quiet = member.entries.length === 0 && member.absences.length === 0;
	return (
		<section aria-label={member.name} className="space-y-2">
			<div className="flex items-baseline gap-2 flex-wrap text-[12.5px]">
				<span className="font-bold text-foreground">{member.name}</span>
				<span className="text-muted-foreground">shared {describeShareFrom(member.sharedFrom)}</span>
				{!member.active && <span className="text-muted-foreground">· no longer assigned</span>}
				<span className="ml-auto font-mono font-bold text-foreground">
					{hoursText(member.hours)}
				</span>
			</div>
			{member.balance ? (
				<p className="text-[12.5px] text-foreground font-medium">
					Balance {balanceText(member.balance.balance)}, as of {dayText(member.balance.asOf)}.
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
					{member.absences.length > 0 && (
						<div>
							<p className={LABEL}>Absences</p>
							<ul className="text-[12.5px] text-foreground space-y-0.5">
								{member.absences.map((absence) => (
									<li key={`${absence.date}-${absence.type}`}>
										{formatDateOnly(absence.date)} · {absence.type}
										{absence.halfDay && " · half day"}
									</li>
								))}
							</ul>
						</div>
					)}
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
	const record = query.data;
	const name = record?.organisation.name ?? "";
	const title = variant === "visible" ? `What ${name} sees` : `${name}'s record`;
	const entriesInMonth = (record?.projects ?? []).some((p) =>
		p.members.some((m) => m.entries.length > 0 || m.absences.length > 0),
	);

	let body: React.ReactNode;
	if (query.error) {
		const forbidden = query.error instanceof ApiError && query.error.statusCode === 403;
		body = (
			<Panel role="alert" padding="px-6 py-[22px]">
				<p className="font-heading text-lg font-extrabold text-foreground">
					{forbidden ? "Admins only." : "The record could not be read."}
				</p>
				{!forbidden && (
					<p className="mt-1 text-xs text-muted-foreground">
						{describeError(query.error, "Nothing came back.")}
					</p>
				)}
			</Panel>
		);
	} else if (!record) {
		body = <p className="text-sm text-muted-foreground px-2">Loading…</p>;
	} else if (!entriesInMonth) {
		body = (
			<Panel padding="px-6 py-[22px]">
				<p className="font-heading text-lg font-extrabold text-foreground">
					No entries in {monthTitle(month)}.
				</p>
			</Panel>
		);
	} else {
		body = record.projects.map(({ project, members }) => (
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
					<span className="text-[12.5px] text-muted-foreground">{KIND_LABELS[project.kind]}</span>
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
		));
	}

	return (
		<div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-5 pb-24">
			<header className="space-y-1">
				<h1 className={TITLE}>{record ? title : "Loading…"}</h1>
				{variant === "visible" && record && (
					<p className="text-sm font-medium text-foreground/90">
						This is the data {name} holds about you, read through the same query it uses.
					</p>
				)}
				<Link to={`/organisations/${id}`} className={LINKISH}>
					Back to {name || "the organisation"}
				</Link>
			</header>

			<div className="flex items-center gap-3 flex-wrap">
				<div className="inline-flex items-center gap-1 rounded-full bg-sidebar shadow-soft p-1">
					<button
						type="button"
						onClick={() => setMonth(prevMonth(month))}
						aria-label="Previous month"
						className={SKY_NAV}
					>
						<ChevronLeft className="w-4 h-4" aria-hidden="true" />
					</button>
					<h2
						className="px-2 font-heading text-[15px] font-extrabold text-foreground whitespace-nowrap"
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
						className={SKY_NAV}
					>
						<ChevronRight className="w-4 h-4" aria-hidden="true" />
					</button>
				</div>
				{!current && (
					<button
						type="button"
						onClick={() => setMonth(monthOf(today))}
						className={cn(LINKISH, "rounded-full bg-sidebar shadow-soft px-3 py-1.5")}
					>
						This month
					</button>
				)}
			</div>

			{body}
		</div>
	);
}
