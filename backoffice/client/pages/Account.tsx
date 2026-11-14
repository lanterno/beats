/**
 * One account: its state, what it holds as counts, where its coach money is
 * going, and the acts available on it. Operational metadata throughout —
 * how big, never what (docs/backoffice.md § The line), which the page says
 * out loud rather than leaving as an absence.
 *
 * The page leads with a sentence about what, if anything, is worth knowing,
 * because the operator arrives here from a mail or an alert and needs the
 * answer before the facts.
 */

import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect } from "react";
import { Link, useParams } from "react-router";
import { get } from "@/shared/api/client";
import type { AccountDetail, DayFigure } from "@/shared/api/schema";
import { ACCOUNT_COMMANDS } from "@/shared/commands";
import { dayOf, dollars, everyDay, formatBytes, whole } from "@/shared/lib/format";
import { rememberOpened } from "@/shared/lib/recent";
import {
	Chip,
	DayBars,
	day,
	Empty,
	Facts,
	Failed,
	Id,
	Loading,
	Meter,
	Page,
	Pair,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

/** How much of the coach bar chart to draw: the month's shape, as the API's
 * own window (`ACCOUNT_COACH_SPEND_DAYS`). */
const COACH_DAYS = 30;

/**
 * The sentence at the top. Only things the API actually answers: whether it
 * is suspended, and how close the coach spend is to a cap it has.
 */
export function accountHeadline(detail: AccountDetail): string {
	if (detail.suspended_at) {
		const kind = detail.suspended_kind ? ` for ${detail.suspended_kind}` : "";
		return `This account is suspended${kind}.`;
	}
	const budget = detail.coach_budget_usd;
	const spend = detail.coach_spend_usd ?? 0;
	if (budget && budget > 0) {
		const share = spend / budget;
		if (share >= 1) return "This account has spent its coach cap for the month.";
		if (share >= 0.8) return "This account is near its coach cap.";
	}
	return "Nothing about this account needs you.";
}

function Marks({ detail }: { detail: AccountDetail }) {
	return (
		<div className="mb-5 flex flex-wrap items-center gap-2">
			<span className="rounded-full bg-panel-solid px-3 py-1 shadow-[var(--shadow-hairline)]">
				<Id>{detail.id}</Id>
			</span>
			<span className="rounded-full bg-panel-solid px-3 py-1 text-[13px] break-all shadow-[var(--shadow-hairline)]">
				{detail.email}
			</span>
			<Chip tone={detail.suspended_at ? "owed" : "good"}>
				{detail.suspended_at ? "Suspended" : "Active"}
			</Chip>
			<span className="text-[13px] text-ink-on-sky">
				Created {dayOf(detail.created_at)} · Last seen {dayOf(detail.last_seen_on)}
			</span>
		</div>
	);
}

/** A count with its label, in the mock's row of tiles. */
function Tile({ label, value }: { label: string; value: ReactNode }) {
	return (
		<div className="rounded-[var(--radius-card)] bg-panel px-5 py-4 shadow-[var(--shadow-hairline)]">
			<p className="text-[13px] text-ink-muted">{label}</p>
			<p className="font-heading text-[26px] leading-tight font-extrabold">{value}</p>
		</div>
	);
}

function CoachSpend({ detail, id }: { detail: AccountDetail; id: string }) {
	const spend = useQuery({
		queryKey: ["account-coach", id],
		queryFn: () => get<DayFigure[]>(`/api/operator/accounts/${id}/coach`),
	});
	const budget = detail.coach_budget_usd;
	const total = detail.coach_spend_usd ?? 0;
	const days = spend.data ? everyDay(spend.data, COACH_DAYS, new Date()) : [];
	const said = `Coach cost a day over the last ${COACH_DAYS} days.`;

	return (
		<Panel raised title="Coach spend" note={`Dollars a day, last ${COACH_DAYS} days.`}>
			<div className="px-6 pb-1">
				<p className="font-heading text-[30px] leading-tight font-extrabold">
					{dollars(total)}{" "}
					<span className="font-body text-[15px] font-normal text-ink-muted">
						{budget ? `of a ${dollars(budget)} cap this month` : "this month, no cap set"}
					</span>
				</p>
				{budget ? (
					<div className="mt-2 mb-1">
						<Meter value={total} max={budget} label="Coach spend against the monthly cap" />
					</div>
				) : null}
			</div>
			{spend.error ? <Failed bare error={spend.error} onRetry={() => spend.refetch()} /> : null}
			{spend.data ? (
				days.some((d) => d.value > 0) ? (
					<DayBars days={days} said={said} unit="Spent" show={dollars} />
				) : (
					<Empty title="No coach calls in the last 30 days." />
				)
			) : spend.error ? null : (
				<Loading />
			)}
		</Panel>
	);
}

function History({ id }: { id: string }) {
	const audit = useQuery({
		queryKey: ["account-audit", id],
		queryFn: () => get<Array<Record<string, unknown>>>(`/api/operator/accounts/${id}/audit`),
	});
	return (
		<Panel
			title="What has been done to this account"
			note="From the back office, by the runner. Opening the account is a read and is not in here."
		>
			{audit.error ? <Failed bare error={audit.error} onRetry={() => audit.refetch()} /> : null}
			{audit.data ? (
				<Table
					head={[day("When"), "Command", "Operator", "What changed"]}
					rows={audit.data.map((r) => [
						typeof r.at === "string" ? r.at.slice(0, 16).replace("T", " ") : "—",
						String(r.command ?? "—"),
						<span key="who" className="break-words">
							{String(r.operator_email ?? "—")}
						</span>,
						<code key="change" className="text-[13px] break-words">
							{JSON.stringify(r.after ?? {})}
						</code>,
					])}
					empty={
						<Empty title="Nothing has been done to this account.">
							Every command the back office runs on it lands here.
						</Empty>
					}
				/>
			) : audit.error ? null : (
				<Loading />
			)}
		</Panel>
	);
}

export function Account() {
	const { id = "" } = useParams();
	const { data, error, refetch } = useQuery({
		queryKey: ["account", id],
		queryFn: () => get<AccountDetail>(`/api/operator/accounts/${id}`),
	});

	// Ids only, in this browser, and only once the account resolved: a
	// mistyped id is not something to offer again.
	useEffect(() => {
		if (data) rememberOpened(data.id);
	}, [data]);

	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	return (
		<Page
			title={accountHeadline(data)}
			back={{ to: "/accounts", label: "Find another account" }}
			lead={
				data.suspended_at
					? `Suspended since ${dayOf(data.suspended_at)}${data.suspended_by ? ", by the back office" : ""}. Nothing it holds has been touched.`
					: "What it is, how big it is, and what can be done about it."
			}
		>
			<Marks detail={data} />
			<CoachSpend detail={data} id={id} />
			<div className="grid grid-cols-2 gap-[18px] sm:grid-cols-4">
				<Tile label="Projects" value={whole(data.projects)} />
				<Tile label="Sessions" value={whole(data.sessions)} />
				<Tile label="Devices" value={whole((data.devices ?? []).length)} />
				<Tile label="Stored, estimated" value={formatBytes(data.storage_bytes ?? 0)} />
			</div>
			<Panel title="Devices" note="Revoking asks the device to pair again.">
				<Table
					head={["Device", day("Paired"), day("Last seen"), "State", ""]}
					rows={(data.devices ?? []).map((d) => [
						<Id key={d.device_id}>{d.device_id}</Id>,
						dayOf(d.created_at),
						dayOf(d.last_seen),
						<Chip key="state" tone={d.revoked ? "quiet" : "good"}>
							{d.revoked ? "Revoked" : "Paired"}
						</Chip>,
						d.revoked ? null : (
							<CommandForm
								key={`revoke-${d.device_id}`}
								inline
								name="device.revoke"
								label={`Revoke device ${d.device_id}`}
								action="Revoke"
								args={{ user_id: data.id, device_id: d.device_id }}
								invalidates={["account"]}
							/>
						),
					])}
					empty={
						<Empty title="No devices are paired.">
							A paired wall clock or daemon shows up here.
						</Empty>
					}
				/>
			</Panel>
			<Pair>
				<Panel title="Connected" note="Which services, never what they hold.">
					<Facts
						items={[
							["Integrations", data.integrations?.join(", ") || "None"],
							["Passkeys", whole(data.passkeys)],
							["Single sign-on", data.sso_providers?.join(", ") || "None"],
							["Signed out everywhere", dayOf(data.sessions_valid_after)],
							["Limits overridden", data.limits_overridden ? "Yes" : "No"],
							["Biometric rows", whole(data.biometric_rows)],
						]}
					/>
				</Panel>
				<Panel title="Organisations">
					<Table
						head={["Organisation", "Role", "Membership"]}
						rows={(data.organisations ?? []).map((m) => [
							<Link
								key={m.organisation_id}
								to={`/organisations/${m.organisation_id}`}
								className="link"
							>
								{m.organisation_name || m.organisation_id}
							</Link>,
							m.role,
							<Chip key="state" tone={m.active ? "good" : "quiet"}>
								{m.active ? "Active" : "Ended"}
							</Chip>,
						])}
						empty={<Empty title="Not a member of any organisation." />}
					/>
				</Panel>
			</Pair>
			<Acts detail={data} />
			<History id={id} />
			<Panel title="Out of reach here">
				<Prose>
					Sessions, project names, notes, coach conversations and integration tokens. There is no
					way to view the app as this person, and a test plants a sentinel in each of those and
					fails if one reaches this page.
				</Prose>
			</Panel>
		</Page>
	);
}

/**
 * The acts, each a link to its review rather than a form here: the operator
 * reads what will change, who notices and whether it can be taken back
 * before anything is typed (docs/backoffice.md § Commands — the dangerous
 * act must not be the easiest thing on the page).
 *
 * Which acts are offered is this page's to decide, from the state it already
 * has; what each one does is the runner's, and the review asks it.
 */
function Acts({ detail }: { detail: AccountDetail }) {
	const offered = ACCOUNT_COMMANDS.filter((spec) =>
		spec.name === "account.suspend"
			? !detail.suspended_at
			: spec.name === "account.unsuspend"
				? Boolean(detail.suspended_at)
				: true,
	);
	const [contain, grave] = [offered.filter((s) => !s.grave), offered.filter((s) => s.grave)];

	const rail = (specs: typeof offered) =>
		specs.map((spec) => (
			<Link
				key={spec.name}
				to={`/review/${spec.name}/${detail.id}`}
				className={`flex min-h-10 items-center rounded-full px-4 py-2 text-[14px] ${
					spec.grave
						? "bg-persimmon/15 font-bold text-persimmon-ink"
						: "bg-wash hover:bg-wash-strong"
				}`}
			>
				{spec.title}
			</Link>
		));

	return (
		<Pair>
			<Panel title="Contain" note="Each one shows you what will change before it runs.">
				<div className="flex flex-col gap-2 px-6 pb-5">{rail(contain)}</div>
			</Panel>
			<Panel danger title="Suspend or erase" note="Each asks for the account's email, typed back.">
				<div className="flex flex-col gap-2 px-6 pb-5">{rail(grave)}</div>
				<Prose>
					An erasure waits out a window you can still stop it in, and keeps each organisation's
					working-time record under a tombstone, as PRIVACY.md promises.
				</Prose>
			</Panel>
		</Pair>
	);
}
