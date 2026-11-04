/**
 * Found by exact email or id, never browsed: the common entry is a support
 * or erasure mail carrying a full address, and exact match is useless for
 * fishing. The address travels in the POST body, never a URL a request log
 * keeps.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { get, post } from "@/shared/api/client";
import type { AccountDetail, AccountMatch } from "@/shared/api/schema";
import { dayOf, formatBytes } from "@/shared/lib/format";
import { Facts, Failed, Loading, Section, Table } from "@/shared/ui";

export function Accounts() {
	const [email, setEmail] = useState("");
	const lookup = useMutation({
		mutationFn: (address: string) =>
			post<AccountMatch[]>("/api/operator/accounts/lookup", { email: address }),
	});

	return (
		<Section title="Find an account">
			<form
				className="flex gap-2 p-3"
				onSubmit={(e) => {
					e.preventDefault();
					if (email.trim()) lookup.mutate(email.trim());
				}}
			>
				<input
					type="email"
					value={email}
					onChange={(e) => setEmail(e.target.value)}
					placeholder="the exact address, as the mail carries it"
					className="flex-1 border border-neutral-300 rounded px-2 py-1 text-sm"
				/>
				<button
					type="submit"
					className="border border-neutral-300 rounded px-3 py-1 text-sm bg-neutral-50"
				>
					Look up
				</button>
			</form>
			{lookup.error ? <Failed error={lookup.error} /> : null}
			{lookup.data ? (
				<Table
					head={["Account", "Created", "Last seen", "State"]}
					rows={lookup.data.map((m) => [
						<Link key={m.id} to={`/accounts/${m.id}`} className="underline">
							{m.email}
						</Link>,
						dayOf(m.created_at),
						dayOf(m.last_seen_on),
						m.suspended ? "suspended" : "active",
					])}
				/>
			) : null}
		</Section>
	);
}

export function Account() {
	const { id } = useParams();
	const { data, error } = useQuery({
		queryKey: ["account", id],
		queryFn: () => get<AccountDetail>(`/api/operator/accounts/${id}`),
	});
	if (error) return <Failed error={error} />;
	if (!data) return <Loading />;

	return (
		<>
			<Section title={data.email}>
				<Facts
					items={[
						["Created", dayOf(data.created_at)],
						["Last seen", dayOf(data.last_seen_on)],
						[
							"State",
							data.suspended_at
								? `suspended (${data.suspended_kind ?? "?"}, since ${dayOf(data.suspended_at)}, by ${data.suspended_by ?? "?"})`
								: "active",
						],
						["Signed out everywhere", dayOf(data.sessions_valid_after)],
						["Passkeys", data.passkeys],
						["Sign-in providers", data.sso_providers?.join(", ") || "none"],
						["Integrations", data.integrations?.join(", ") || "none"],
						["Limits overridden", data.limits_overridden ? "yes" : "no"],
					]}
				/>
			</Section>
			<Section title="What it stores — how big, never what">
				<Facts
					items={[
						["Projects", data.projects],
						["Sessions", data.sessions],
						["Biometric rows", data.biometric_rows],
						["Storage estimate", formatBytes(data.storage_bytes ?? 0)],
						[
							"Coach spend this month",
							`$${(data.coach_spend_usd ?? 0).toFixed(2)} of $${(data.coach_budget_usd ?? 0).toFixed(2)}`,
						],
					]}
				/>
			</Section>
			<Section title="Devices">
				<Table
					head={["Device", "Created", "Last seen", "State"]}
					rows={(data.devices ?? []).map((d) => [
						<code key={d.device_id} className="text-xs">
							{d.device_id}
						</code>,
						dayOf(d.created_at),
						dayOf(d.last_seen),
						d.revoked ? "revoked" : "paired",
					])}
				/>
			</Section>
			<Section title="Organisations">
				<Table
					head={["Organisation", "Role", "Membership"]}
					rows={(data.organisations ?? []).map((m) => [
						<Link
							key={m.organisation_id}
							to={`/organisations/${m.organisation_id}`}
							className="underline"
						>
							{m.organisation_name || m.organisation_id}
						</Link>,
						m.role,
						m.active ? "active" : "ended",
					])}
				/>
			</Section>
		</>
	);
}
