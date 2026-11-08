/**
 * Found by exact email or id, never browsed: the common entry is a support
 * or erasure mail carrying a full address, and exact match is useless for
 * fishing. The address travels in the POST body, never a URL a request log
 * keeps.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { Link, useParams } from "react-router";
import { get, post } from "@/shared/api/client";
import type { AccountDetail, AccountMatch } from "@/shared/api/schema";
import { dayOf, dollars, formatBytes, whole } from "@/shared/lib/format";
import {
	buttonClass,
	Chip,
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

export function Accounts() {
	const [email, setEmail] = useState("");
	const lookup = useMutation({
		mutationFn: (address: string) =>
			post<AccountMatch[]>("/api/operator/accounts/lookup", { email: address }),
	});

	return (
		<Page
			title="Find an account"
			lead="By its exact address, as the mail carries it. Accounts can't be browsed from here, and the address never goes in a URL."
		>
			<Panel raised>
				<form
					className="flex flex-wrap items-end gap-3 p-6"
					onSubmit={(e) => {
						e.preventDefault();
						if (email.trim()) lookup.mutate(email.trim());
					}}
				>
					<TextField
						label="Email address"
						type="email"
						value={email}
						onChange={(e) => setEmail(e.target.value)}
						className="min-w-[15rem] flex-1"
					/>
					<button type="submit" disabled={lookup.isPending} className={buttonClass("primary")}>
						{lookup.isPending ? "Looking…" : "Find this account"}
					</button>
				</form>
			</Panel>
			{lookup.error ? <Failed error={lookup.error} /> : null}
			{lookup.data ? (
				<Panel title={lookup.data.length > 0 ? "What came back" : undefined}>
					<div className={lookup.data.length > 0 ? "" : "pt-4"}>
						<Table
							head={["Account", day("Created"), day("Last seen"), "State"]}
							rows={lookup.data.map((m) => [
								<Link key={m.id} to={`/accounts/${m.id}`} className="link">
									{m.email}
								</Link>,
								dayOf(m.created_at),
								dayOf(m.last_seen_on),
								<Chip key="state" tone={m.suspended ? "owed" : "good"}>
									{m.suspended ? "Suspended" : "Active"}
								</Chip>,
							])}
							empty={
								<Empty title="No account has that address.">
									It has to match exactly, so check it against the mail it came in.
								</Empty>
							}
						/>
					</div>
				</Panel>
			) : null}
		</Page>
	);
}

function seen(detail: AccountDetail): string {
	const joined = detail.created_at ? `Joined ${dayOf(detail.created_at)}. ` : "";
	return `${joined}${detail.last_seen_on ? `Last seen ${dayOf(detail.last_seen_on)}.` : "Not seen since."}`;
}

export function Account() {
	const { id } = useParams();
	const { data, error, refetch } = useQuery({
		queryKey: ["account", id],
		queryFn: () => get<AccountDetail>(`/api/operator/accounts/${id}`),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const budget = data.coach_budget_usd;
	const spend = data.coach_spend_usd ?? 0;

	return (
		<Page
			title={data.email}
			back={{ to: "/accounts", label: "Find another account" }}
			lead={
				data.suspended_at
					? `Suspended${data.suspended_kind ? ` for ${data.suspended_kind}` : ""} since ${dayOf(data.suspended_at)}.`
					: seen(data)
			}
			aside={
				<div className="mt-2.5 rounded-full bg-panel-solid">
					{data.suspended_at ? <Chip tone="owed">Suspended</Chip> : <Chip tone="good">Active</Chip>}
				</div>
			}
		>
			<Pair>
				<Panel title="The account">
					<Facts
						items={[
							["Created", dayOf(data.created_at)],
							["Last seen", dayOf(data.last_seen_on)],
							...(data.suspended_at
								? ([
										["Suspended by", <Id key="by">{data.suspended_by ?? "not recorded"}</Id>],
									] as Array<[string, ReactNode]>)
								: []),
							["Signed out everywhere", dayOf(data.sessions_valid_after)],
							["Passkeys", data.passkeys],
							["Sign-in providers", data.sso_providers?.join(", ") || "None"],
							["Integrations", data.integrations?.join(", ") || "None"],
							["Limits overridden", data.limits_overridden ? "Yes" : "No"],
						]}
					/>
				</Panel>
				<Panel title="What it stores" note="How big, never what.">
					<Facts
						items={[
							["Projects", whole(data.projects)],
							["Sessions", whole(data.sessions)],
							["Biometric rows", whole(data.biometric_rows)],
							["Storage estimate", formatBytes(data.storage_bytes ?? 0)],
							[
								"Coach spend this month",
								budget ? (
									<div key="coach" className="w-40">
										<p className="mb-1">
											{dollars(spend)} of {dollars(budget)}
										</p>
										<Meter value={spend} max={budget} label="Coach spend against the monthly cap" />
									</div>
								) : (
									`${dollars(spend)}, no cap set`
								),
							],
						]}
					/>
				</Panel>
			</Pair>
			<Panel title="Devices">
				<Table
					head={["Device", day("Created"), day("Last seen"), "State", ""]}
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
			<AccountActions detail={data} />
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
		</Page>
	);
}

/**
 * The account commands, each through the one runner. Suspension and erasure
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
			<Panel title="Controls">
				{detail.suspended_at ? (
					<CommandForm
						name="account.unsuspend"
						label="Unsuspend"
						action="Unsuspend this account"
						args={{ user_id: detail.id }}
						invalidates={["account", "attention"]}
					/>
				) : null}
				<CommandForm
					name="account.sign_out_everywhere"
					label="Sign out everywhere"
					about="Every session it has open stops working."
					action="Sign this account out"
					args={{ user_id: detail.id }}
					invalidates={["account"]}
				/>
				<CommandForm
					name="account.set_limits"
					label="Set limits"
					about="An empty box means the platform's default."
					action="Save these limits"
					args={limitArgs}
					invalidates={["account"]}
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
					invalidates={["account"]}
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
						invalidates={["account", "attention"]}
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
					label="Queue erasure"
					about="Waits out a 7-day window before it runs."
					action="Queue this erasure"
					done="Queued. Cancel it from Compliance inside the week."
					args={{ user_id: detail.id }}
					confirmHint="Type the account's email to confirm"
					invalidates={["account", "operator-jobs", "attention"]}
				/>
				<div className="border-t border-hairline pt-4">
					<Prose>
						Queueing an erasure suspends the account with the erasure's own wording, which names the
						day the window ends. The deletion keeps each organisation's working-time record under a
						tombstone, as PRIVACY.md promises.
					</Prose>
				</div>
			</Panel>
		</>
	);
}
