/**
 * What PRIVACY.md and the DPA promise, and the one act that keeps it: the
 * platform-wide retention purge, never scheduled, started by an operator
 * behind the typed word "all". The purge waits a day in the queue; an
 * erasure is queued from the account's own page.
 */

import { Link } from "react-router";
import { Page, Panel, Prose } from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

export function Compliance() {
	return (
		<Page
			title="Compliance"
			lead="The retention promise, kept by hand: an operator runs the purge, by decision, and nothing runs it for them."
		>
			<Panel
				danger
				raised
				title="Retention purge, platform-wide"
				note="Never scheduled, by decision: PRIVACY.md and the DPA promise an operator runs it."
			>
				<CommandForm
					name="retention.purge"
					label="Purge every organisation"
					about="Removes each organisation's records past its retention, and trims this back office's own audit at four years."
					action="Queue the purge"
					done="Queued. Cancel it from Jobs inside the day."
					args={{ organisation_id: null }}
					confirmHint='Type "all" to confirm'
					invalidates={["operator-jobs"]}
				/>
			</Panel>
			<Panel title="Where the rest is">
				<Prose>
					A purge waits a day under{" "}
					<Link to="/jobs" className="link">
						Jobs
					</Link>
					, where it can still be cancelled. One organisation alone is purged from its own page
					while it has no owner, and an erasure is queued from the account's page, where it waits
					seven days. Everything that has been run is under{" "}
					<Link to="/audit" className="link">
						Audit
					</Link>
					.
				</Prose>
			</Panel>
		</Page>
	);
}
