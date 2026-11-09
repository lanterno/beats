/**
 * Found by exact address or id, never browsed: the common entry is a support
 * or erasure mail carrying a full address, and an exact match is useless for
 * fishing. The address travels in the POST body, never a URL a request log
 * keeps for thirty days.
 *
 * Opening an account is a read, and reads are not recorded — the page says
 * so, because the absence is a decision and not an oversight. "You opened
 * recently" is this browser's own list of ids (shared/lib/recent.ts).
 */

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { post } from "@/shared/api/client";
import type { AccountMatch } from "@/shared/api/schema";
import { dayOf } from "@/shared/lib/format";
import { type Opened, RECENT_DAYS, readRecent } from "@/shared/lib/recent";
import {
	buttonClass,
	Chip,
	day,
	Empty,
	Failed,
	Id,
	Page,
	Pair,
	Panel,
	Prose,
	Table,
	TextField,
} from "@/shared/ui";

/** A Mongo id, typed straight in. Anything else is treated as an address. */
const IDENTIFIER = /^[0-9a-f]{24}$/i;

/** What the operator typed: an id opens a page, an address needs the lookup. */
export function looksLikeId(typed: string): boolean {
	return IDENTIFIER.test(typed.trim());
}

function Recent({ entries }: { entries: Opened[] }) {
	return (
		<Panel
			title="You opened recently"
			note={`Ids only, kept in this browser, cleared after ${RECENT_DAYS} days. It is not a record of anything: only you can see it.`}
		>
			<Table
				head={["Account", day("Opened")]}
				rows={entries.map((e) => [
					<Link key={e.id} to={`/accounts/${e.id}`} className="link">
						<Id>{e.id}</Id>
					</Link>,
					e.day,
				])}
				empty={<Empty title="Nothing yet.">An account you open shows up here for a week.</Empty>}
			/>
		</Panel>
	);
}

export function Accounts() {
	const [typed, setTyped] = useState("");
	const navigate = useNavigate();
	// Read once per mount: it changes when you open an account, and opening
	// one leaves this page.
	const [recent] = useState(() => readRecent());
	const lookup = useMutation({
		mutationFn: (address: string) =>
			post<AccountMatch[]>("/api/operator/accounts/lookup", { email: address }),
	});

	const submit = (e: React.FormEvent) => {
		e.preventDefault();
		const wanted = typed.trim();
		if (!wanted) return;
		if (looksLikeId(wanted)) {
			navigate(`/accounts/${wanted}`);
			return;
		}
		lookup.mutate(wanted);
	};

	return (
		<Page
			title="Who are you looking for?"
			lead="You need the whole address or the account id. There is no list of people here and no search over what they wrote, so you only ever open the account you came for."
		>
			<Panel raised>
				<form className="flex flex-wrap items-end gap-3 px-6 pt-5 pb-4" onSubmit={submit}>
					<TextField
						label="Exact address or account id"
						value={typed}
						onChange={(e) => setTyped(e.target.value)}
						placeholder="maya@example.com"
						autoComplete="off"
						spellCheck={false}
						className="min-w-[18rem] flex-1"
					/>
					<button type="submit" disabled={lookup.isPending} className={buttonClass("primary")}>
						{lookup.isPending ? "Looking…" : "Find this account"}
					</button>
				</form>
				{lookup.error ? <Failed bare error={lookup.error} /> : null}
				{lookup.data ? (
					<div className="border-t border-hairline pt-2">
						<Table
							head={["Account", day("Created"), day("Last seen"), "State", ""]}
							rows={lookup.data.map((m) => [
								<span key="who" className="break-all">
									{m.email}
								</span>,
								dayOf(m.created_at),
								dayOf(m.last_seen_on),
								<Chip key="state" tone={m.suspended ? "owed" : "good"}>
									{m.suspended ? "Suspended" : "Active"}
								</Chip>,
								<Link key="open" to={`/accounts/${m.id}`} className={buttonClass("secondary")}>
									Open this account
								</Link>,
							])}
							empty={
								<Empty title="No account has that address.">
									It has to match exactly, so check it against the mail it came in. The same address
									spelled with different capitals can be two accounts, and both would show here.
								</Empty>
							}
						/>
					</div>
				) : null}
			</Panel>
			<Pair>
				<Recent entries={recent} />
				<Panel title="What you will see">
					<Prose>
						State, dates, counts, spend, connected services, devices and memberships. Enough to fix
						what is wrong.
					</Prose>
					<Prose>
						Not sessions, projects, notes, or coach conversations. Those belong to the person, and
						nothing here can open them.
					</Prose>
					<p className="px-6 pb-5 text-[14px] text-ink-muted">
						Opening an account is a read, and reads are not recorded. The audit holds what was{" "}
						<em>done</em>.
					</p>
				</Panel>
			</Pair>
		</Page>
	);
}
