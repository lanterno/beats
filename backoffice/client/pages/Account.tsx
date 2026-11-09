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
import { type ReactNode, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { get } from "@/shared/api/client";
import type { AccountDetail, DayFigure } from "@/shared/api/schema";
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
	TextField,
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
			<AccountActions detail={data} />
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
 * The account commands, each through the one runner. They sit in the main
 * column rather than the mock's right rail because each is still a form
 * with its fields: the rail's one-line buttons arrive with the review step,
 * which is what they will open.
 * Suspension and erasure
 * demand the account's email typed back — proof the operator is acting on
 * the thing they think they are, never a cross-site defence (the Origin
 * check holds that line). Suspend and unsuspend each show only in the state
 * they apply to.
 */
function AccountActions({ detail }: { detail: AccountDetail }) {
	const [reason, setReason] = useState("");
	const [limits, setLimits] = useState({
		coach: "",
		beats: "",
		signals: "",
		imports: "",
		webhooksOff: false,
	});

	const limitArgs: Record<string, unknown> = {
		user_id: detail.id,
		coach_monthly_budget_usd: limits.coach ? Number(limits.coach) : null,
		writes_per_minute_beats: limits.beats ? Number(limits.beats) : null,
		writes_per_minute_signals: limits.signals ? Number(limits.signals) : null,
		imports_per_hour: limits.imports ? Number(limits.imports) : null,
		webhooks_disabled: limits.webhooksOff,
	};

	const numberField = (key: "coach" | "beats" | "signals" | "imports", label: string) => (
		<TextField
			key={key}
			label={label}
			value={limits[key]}
			onChange={(e) => setLimits({ ...limits, [key]: e.target.value })}
			inputMode="numeric"
			className="w-32"
		/>
	);

	return (
		<>
			<Panel title="Contain" note="Each one tells you what it changed once it has run.">
				{detail.suspended_at ? (
					<CommandForm
						name="account.unsuspend"
						label="Unsuspend"
						action="Unsuspend this account"
						args={{ user_id: detail.id }}
						invalidates={["account", "account-audit", "attention"]}
					/>
				) : null}
				<CommandForm
					name="account.sign_out_everywhere"
					label="Sign out everywhere"
					about="Every session it has open stops working."
					action="Sign this account out"
					args={{ user_id: detail.id }}
					invalidates={["account", "account-audit"]}
				/>
				<CommandForm
					name="account.set_limits"
					label="Set limits on writes or webhooks"
					about="An empty box means the platform's default."
					action="Save these limits"
					args={limitArgs}
					invalidates={["account", "account-audit"]}
					fields={
						<>
							{numberField("coach", "Coach $ a month")}
							{numberField("beats", "Beat writes a minute")}
							{numberField("signals", "Signal writes a minute")}
							{numberField("imports", "Imports an hour")}
							<label className="flex h-10 items-center gap-2 text-[14px]">
								<input
									type="checkbox"
									checked={limits.webhooksOff}
									onChange={(e) => setLimits({ ...limits, webhooksOff: e.target.checked })}
									className="size-4 accent-[var(--leaf)]"
								/>
								Webhooks off
							</label>
						</>
					}
				/>
				<CommandForm
					name="account.clear_limits"
					label="Clear limits"
					about="Back to the platform's defaults."
					action="Clear all limits"
					args={{ user_id: detail.id }}
					invalidates={["account", "account-audit"]}
				/>
			</Panel>
			<Panel
				danger
				title="Suspend or erase"
				note="Each one asks for the account's email, so you know it's the account you mean."
			>
				{detail.suspended_at ? null : (
					<CommandForm
						name="account.suspend"
						label="Suspend for abuse"
						action="Suspend this account"
						args={{ user_id: detail.id, kind: "abuse", reason }}
						confirmHint="Type the account's email to confirm"
						invalidates={["account", "account-audit", "attention"]}
						fields={
							<TextField
								label="Reason, for the record (never shown)"
								value={reason}
								onChange={(e) => setReason(e.target.value)}
								className="min-w-[15rem] flex-1"
							/>
						}
					/>
				)}
				<CommandForm
					name="account.erase"
					label="Erase this account"
					about="Deletes everything they have, seven days after you queue it, and only when they asked for it. It suspends the account while it waits."
					action="Queue this erasure"
					done="Queued. Cancel it from Jobs and windows inside the week."
					args={{ user_id: detail.id }}
					confirmHint="Type the account's email to confirm"
					invalidates={["account", "account-audit", "operator-jobs", "attention"]}
				/>
				<div className="border-t border-hairline pt-4">
					<Prose>
						The deletion keeps each organisation's working-time record under a tombstone, as
						PRIVACY.md promises. Everything else goes.
					</Prose>
				</div>
			</Panel>
		</>
	);
}
