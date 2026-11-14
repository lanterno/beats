/**
 * The organisations the platform runs for: states, counts by role and the
 * audit of acts — settings and counts, never a figure from anyone's record,
 * and never a roster: the API answers how many hold each role, not who.
 * The operator acts here only for an organisation with no owner, and only
 * when asked; each act is a link into its review, and is refused
 * server-side the moment an owner exists (docs/backoffice.md § The
 * operator's organisation acts).
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { get } from "@/shared/api/client";
import type {
	AttentionCounts,
	OrgAuditRow,
	OrganisationDetail,
	OrganisationSummary,
} from "@/shared/api/schema";
import { dayOf, minuteOf } from "@/shared/lib/format";
import {
	type Deletion,
	deletionOf,
	deletionReady,
	eventWords,
	highestRole,
	keepsFor,
	memberCount,
	type OrgGroup,
	organisationHeadline,
	organisationsHeadline,
	rolesOnLadder,
	type Standing,
	standing,
	timesheets,
} from "@/shared/lib/organisations";
import {
	buttonClass,
	Chip,
	day,
	Empty,
	Facts,
	Failed,
	figure,
	Id,
	Loading,
	Page,
	Pair,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";

type Job = Record<string, unknown>;

/** The job queue, read for the deletions waiting on an organisation. A
 * failure here only loses the "Deleting" state, so it is not the page's. */
function useJobs(): readonly Job[] {
	const { data } = useQuery({
		queryKey: ["operator-jobs"],
		queryFn: () => get<Job[]>("/api/operator/jobs"),
	});
	return data ?? [];
}

const FILTERS: Array<{ id: "all" | OrgGroup; label: string }> = [
	{ id: "all", label: "All" },
	{ id: "needs", label: "Needs you" },
	{ id: "leaving", label: "Closing or deleting" },
	{ id: "active", label: "Active" },
];

export function Organisations() {
	const { data, error, refetch } = useQuery({
		queryKey: ["organisations"],
		queryFn: () => get<OrganisationSummary[]>("/api/operator/organisations"),
	});
	const attention = useQuery({
		queryKey: ["attention"],
		queryFn: () => get<AttentionCounts>("/api/operator/attention"),
	});
	const jobs = useJobs();
	const [filter, setFilter] = useState<"all" | OrgGroup>("all");
	const [query, setQuery] = useState("");
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const now = new Date();
	const rows: Array<{ o: OrganisationSummary; s: Standing }> = data.map((o) => ({
		o,
		s: standing(o, deletionOf(jobs, o.id), now),
	}));
	const name = query.trim().toLowerCase();
	const shown = rows.filter(
		({ o, s }) =>
			(filter === "all" || s.group === filter) && (!name || o.name.toLowerCase().includes(name)),
	);

	return (
		<Page
			title={organisationsHeadline(rows.map((r) => r.s))}
			lead="The rest are running themselves. You step in only where nobody is left to act and someone there has asked."
		>
			<div className="flex flex-wrap items-center gap-3">
				<div className="flex flex-wrap gap-1">
					{FILTERS.map(({ id, label }) => (
						<button
							key={id}
							type="button"
							aria-pressed={filter === id}
							onClick={() => setFilter(id)}
							className={`inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] ${
								filter === id ? "bg-panel-solid font-bold" : "hover:bg-wash"
							}`}
						>
							{label}{" "}
							<span className="font-heading">
								{id === "all" ? rows.length : rows.filter((r) => r.s.group === id).length}
							</span>
						</button>
					))}
				</div>
				<label className="ml-auto w-full max-w-[280px]">
					<span className="sr-only">Find an organisation by name</span>
					<input
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="Find an organisation by name"
						className="h-10 w-full rounded-full bg-panel px-4 text-[14px] text-ink shadow-[var(--shadow-hairline)]"
					/>
				</label>
			</div>
			<Panel raised>
				<div className="pt-3">
					<Table
						head={["Organisation", figure("Members"), "Ownership", "Keeps records for", "State"]}
						rows={shown.map(({ o, s }) => [
							<Link key={o.id} to={`/organisations/${o.id}`} className="link font-bold">
								{o.name}
							</Link>,
							memberCount(o.members_by_role),
							<Chip key="ownership" tone={s.ownership.tone}>
								{s.ownership.label}
							</Chip>,
							keepsFor(o.retention_years),
							<Chip key="state" tone={s.state.tone}>
								{s.state.label}
							</Chip>,
						])}
						empty={
							data.length === 0 ? (
								<Empty title="No organisations yet.">
									One appears here as soon as somebody creates it.
								</Empty>
							) : (
								<Empty title="No organisation matches.">
									Clear the filter, or check how the name is spelled.
								</Empty>
							)
						}
					/>
				</div>
			</Panel>
			<Pair>
				<Panel
					title="Slow decisions, for them to make"
					note="You cannot decide these and you should not. Watch them only to spot a workflow that has stopped."
				>
					{attention.error ? (
						<Failed bare error={attention.error} onRetry={() => attention.refetch()} />
					) : attention.data ? (
						<Facts
							items={[
								[
									"Approvals superseded over 30 days ago",
									attention.data.approvals_superseded_over_30d,
								],
								[
									"Absence requests pending over 14 days",
									attention.data.absence_requests_pending_over_14d,
								],
							]}
						/>
					) : (
						<Loading />
					)}
				</Panel>
				<Panel title="Rules that apply here">
					<Prose>
						While an organisation has an owner, nothing here can change it. A suspended owner still
						counts. Project names, team names, clients and the reasons in their audit stay out of
						this page, and so does who its members are.{" "}
						<Link to="/runbooks/organisation-owner" className="link">
							Read the runbook
						</Link>
					</Prose>
				</Panel>
			</Pair>
		</Page>
	);
}

/** What the organisation's page says under its sentence. */
function leadOf(s: OrganisationSummary, deletion: Deletion | null): string {
	if (deletion) {
		return `It goes when its window ends, at ${minuteOf(deletion.run_after)} UTC. Until then the deletion can be cancelled, which is what the window is for.`;
	}
	if (s.owners === 0) {
		return "Nobody can manage its members, its settings or its closing until someone does. You step in only when someone there has asked, by mail from the address on their account.";
	}
	if (s.all_owners_suspended) {
		return "Its owners are still its owners, so nothing here can act on it. Somebody should know, all the same.";
	}
	if (s.closes_on) {
		return "Its owner gave notice. Members can take their projects with them until that day; nothing here can change it.";
	}
	return "While it has an owner, nothing here can change it. Anything it needs is theirs to do.";
}

/** Who did it, as the organisation's audit records it: a member by id, or
 * the operator or the system by kind alone. */
function actorOf(row: OrgAuditRow) {
	if (row.actor_kind === "operator") return "The operator";
	if (row.actor_user_id) return <Id>{row.actor_user_id}</Id>;
	return "The system";
}

export function Organisation() {
	const { id = "" } = useParams();
	const { data, error, refetch } = useQuery({
		queryKey: ["organisation", id],
		queryFn: () => get<OrganisationDetail>(`/api/operator/organisations/${id}`),
	});
	const audit = useQuery({
		queryKey: ["organisation-audit", id],
		queryFn: () => get<OrgAuditRow[]>(`/api/operator/organisations/${id}/audit`),
	});
	const jobs = useJobs();
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;
	const s = data.summary;
	const deletion = deletionOf(jobs, s.id);
	const ownerless = s.owners === 0 && deletion === null;
	const roles = rolesOnLadder(s.members_by_role);
	const review: ReviewOf = (command) => `/review/${command}/${s.id}`;

	return (
		<Page
			title={organisationHeadline(s, deletion)}
			back={{ to: "/organisations", label: "All organisations" }}
			lead={leadOf(s, deletion)}
		>
			<div className="grid items-start gap-[18px] lg:grid-cols-[minmax(0,1fr)_320px]">
				<div className="flex min-w-0 flex-col gap-[18px]">
					{ownerless ? (
						<Panel
							raised
							title="Who asked?"
							note="Only the person who asked can be made owner, and only if nobody active outranks them."
						>
							<Prose>
								The back office does not list who is in an organisation: the API answers how many
								hold each role, never who. Find the person who wrote in by the address the mail came
								from, and give their account id to the review. It says what role they hold here, and
								the highest any active member holds, before anything changes.
							</Prose>
							<Facts items={roles.length ? roles : [["Active members", "Nobody"]]} />
							<div className="flex flex-wrap gap-2 px-6 pt-1 pb-5">
								<Link
									to={review("organisation.grant_owner")}
									className={`${buttonClass("primary")} h-12`}
								>
									Make the requester owner
								</Link>
								<Link to="/accounts" className={`${buttonClass("secondary")} h-12`}>
									Find their account
								</Link>
							</div>
						</Panel>
					) : null}
					<Panel
						title="Their audit log"
						note="What, by whom, to whom and when. The details they wrote are left out. Times are UTC."
					>
						{audit.error ? (
							<Failed bare error={audit.error} onRetry={() => audit.refetch()} />
						) : null}
						{audit.data ? (
							<Table
								head={[day("When"), "What", "By", "To"]}
								rows={audit.data.map((row) => [
									minuteOf(row.at),
									eventWords(row.event),
									actorOf(row),
									row.subject_user_id ? <Id key="to">{row.subject_user_id}</Id> : "—",
								])}
								empty={<Empty title="Nothing recorded yet." />}
							/>
						) : audit.error ? null : (
							<Loading />
						)}
					</Panel>
				</div>
				<aside aria-label="This organisation" className="flex flex-col gap-[18px]">
					<Panel title="This organisation">
						<Facts
							items={[
								["Members", `${memberCount(s.members_by_role)} active`],
								["Highest active role", highestRole(s.members_by_role)],
								["Keeps records for", keepsFor(s.retention_years)],
								["Projects", `${data.projects}, ${data.connected_projects} by a connect`],
								["Active assignments", s.active_assignments],
								["Timesheets", timesheets(data.timesheets_by_status)],
								["Closing", s.closes_on ?? "Not closing"],
								["Created", dayOf(s.created_at)],
							]}
						/>
					</Panel>
					{deletion ? (
						<Panel danger title="Its deletion is queued">
							<Prose>
								It runs from {minuteOf(deletion.run_after)} UTC, and is refused then if the
								organisation has an owner again.
							</Prose>
							<div className="px-6 pb-5">
								<Link
									to={`/review/job.cancel/${deletion.id}`}
									className={`${buttonClass("secondary")} w-full`}
								>
									Review cancelling it
								</Link>
							</div>
						</Panel>
					) : null}
					{ownerless ? <IfNobodyTakesItOn summary={s} review={review} /> : null}
					{ownerless ? <DeleteIt summary={s} review={review} /> : null}
					{s.owners > 0 && s.all_owners_suspended ? (
						<Panel title="Every owner is suspended">
							<Prose>
								A suspended owner is still the owner, or suspending one would hand you their
								organisation. What to check, and who to tell, is in{" "}
								<Link to="/runbooks/organisation-owners-suspended" className="link">
									the runbook
								</Link>
								.
							</Prose>
						</Panel>
					) : null}
				</aside>
			</div>
		</Page>
	);
}

/** The review page of one of this organisation's acts. */
type ReviewOf = (command: string) => string;

/** The closing acts, while nobody is left to act. */
function IfNobodyTakesItOn({
	summary: s,
	review,
}: {
	summary: OrganisationSummary;
	review: ReviewOf;
}) {
	return (
		<Panel
			title="If nobody takes it on"
			note="Only while it has no owner, and only if someone asked."
		>
			{s.closes_on ? (
				<>
					<Prose>
						It closes on {s.closes_on}. Members can take their projects with them until then; a
						later day only gives them more.
					</Prose>
					<div className="flex flex-col gap-2 px-6 pb-5">
						<Link to={review("organisation.begin_closing")} className={buttonClass("secondary")}>
							Move the closing day
						</Link>
						<Link to={review("organisation.cancel_closing")} className={buttonClass("secondary")}>
							Cancel the closing
						</Link>
					</div>
				</>
			) : (
				<>
					<Prose>
						Start closing gives members at least 30 days to take their projects with them.
					</Prose>
					<div className="flex flex-col gap-2 px-6 pb-5">
						<Link to={review("organisation.begin_closing")} className={buttonClass("secondary")}>
							Start closing
						</Link>
					</div>
				</>
			)}
			<Prose>
				Its records past their period can be purged on their own, a day after you queue it.{" "}
				<Link to={`/review/retention.purge/${s.id}`} className="link">
					Review the purge
				</Link>
			</Prose>
		</Panel>
	);
}

/** Deleting it: offered once a deletion queued now would find its closing
 * day come; before that the panel says when it can be. */
function DeleteIt({ summary: s, review }: { summary: OrganisationSummary; review: ReviewOf }) {
	return (
		<Panel danger title="Delete this organisation">
			<Prose>
				Removes the organisation and its audit log, one day after you queue it. Each member is
				handed back their projects first. The back office keeps its own record that this happened.
			</Prose>
			<div className="px-6 pb-5">
				{deletionReady(s.closes_on, new Date()) ? (
					<Link to={review("organisation.delete")} className={`${buttonClass("danger")} w-full`}>
						Review the deletion
					</Link>
				) : (
					<p className="text-[14px] text-ink-muted">
						{s.closes_on
							? `It can be deleted from its closing day, ${s.closes_on}; the deletion can be queued the day before.`
							: "It can be deleted only once it has closed. Start closing first."}
					</p>
				)}
			</div>
		</Panel>
	);
}
