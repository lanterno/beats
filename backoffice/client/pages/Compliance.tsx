/**
 * Privacy and compliance: what was promised about other people's data, and
 * the one control that keeps the promise — the platform-wide retention
 * purge, never scheduled, because PRIVACY.md and the DPA say an operator
 * runs it.
 *
 * The line itself is on this page because it is a promise and not a
 * feature: an operator reading it should be able to tell, before opening
 * any other page, which questions this surface will refuse to answer.
 *
 * What the mock shows and this does not: an erasure request log (its own
 * stage, roadmaps/backoffice.md § 8), backup and restore-drill dates, and a
 * documents checklist. No route answers any of them, and a date with no
 * source is worse here than on any other page.
 */

import { Page, Pair, Panel, Prose } from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

/** docs/backoffice.md § The line, as the operator reads it. */
const LINE: Array<[sees: string, never: string]> = [
	["Account id, address, created, the day last seen, state", "Sessions, their times, their notes"],
	["Counts of projects, sessions, devices and organisations", "Project names, tags, absence notes"],
	["Which integrations are connected", "Any integration's token or what it fetched"],
	["Webhook destinations, by domain", "A webhook's full URL, or what was sent to it"],
	["Coach spend, tokens and model", "Any coach conversation or memory"],
	["Organisation name, settings, members, roles", "Clients, rates, amounts, report contents"],
	["An organisation's audit: what, by whom, to whom, when", "The details of one of its events"],
	["How many biometric rows exist", "Any biometric value"],
];

export function Compliance() {
	return (
		<Page
			title="Privacy and compliance"
			lead="What was promised about other people's data, and the one act that keeps it."
		>
			<Panel
				danger
				title="Retention purge, platform-wide"
				note="Never scheduled, by decision: PRIVACY.md and the DPA promise an operator runs it."
			>
				<CommandForm
					name="retention.purge"
					label="Purge every organisation"
					about="Every organisation's records past its own retention period, and this back office's audit past four years."
					action="Queue the purge"
					done="Queued. Cancel it from Jobs and windows until its window ends."
					args={{ organisation_id: null }}
					confirmHint='Type "all" to confirm'
					invalidates={["operator-jobs", "attention"]}
				/>
			</Panel>
			<Panel
				title="What this back office may see"
				note="The line between running the service and reading someone's life. It is held by construction and by a test that plants a sentinel in every right-hand thing and greps every page for it."
			>
				<div className="overflow-x-auto pb-3">
					<table className="w-full text-[14px]">
						<thead>
							<tr className="text-left text-[13px]">
								<th scope="col" className="px-2.5 py-1.5 pl-6 font-medium text-leaf-ink">
									It sees
								</th>
								<th scope="col" className="px-2.5 py-1.5 pr-6 font-medium text-persimmon-ink">
									It never sees
								</th>
							</tr>
						</thead>
						<tbody>
							{LINE.map(([sees, never]) => (
								<tr key={sees} className="border-t border-hairline">
									<td className="w-1/2 px-2.5 py-[7px] pl-6 align-top">{sees}</td>
									<td className="w-1/2 px-2.5 py-[7px] pr-6 align-top">{never}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			</Panel>
			<Pair>
				<Panel title="Erasure requests">
					<Prose>
						They arrive by email at the address in PRIVACY.md, and there is no log of them here yet.
						An erasure you have queued is on Jobs and windows, where its seven-day window is
						running.
					</Prose>
				</Panel>
				<Panel title="Reading a document in the database">
					<Prose>
						Nothing above stops it, and PRIVACY.md says so rather than pretending otherwise. The
						point of these pages is that the question is answered here instead.
					</Prose>
				</Panel>
			</Pair>
		</Page>
	);
}
