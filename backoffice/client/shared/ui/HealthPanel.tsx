/**
 * Live health (docs/backoffice.md § The pages, Today): availability against
 * the target, the share of 5xx, p95 latency, and active instances against
 * their ceiling. Fails on its own: a Google failure never takes the rest of a
 * page with it.
 */

import { useConsole } from "@/shared/lib/console";
import { whole } from "@/shared/lib/format";
import { freshness, healthHeadline, instancesOf, percent, useHealth } from "@/shared/lib/health";
import { Facts, Failed, Loading, Panel, Prose } from "@/shared/ui";

export function HealthPanel() {
	const health = useHealth();
	const links = useConsole();
	if (health.error) {
		return (
			<Panel title="Health">
				<Failed bare error={health.error} onRetry={() => health.refetch()} />
			</Panel>
		);
	}
	if (!health.data) {
		return (
			<Panel title="Health">
				<Loading />
			</Panel>
		);
	}
	const report = health.data;
	const stale = freshness(report);
	if (report.state === "unavailable" || !report.figures) {
		return (
			<Panel title="Health" note={healthHeadline(report)}>
				<Prose>
					Monitoring answers only on Google Cloud, with the operator allowed to read it.
					{links ? (
						<>
							{" "}
							<a href={links.monitoring} className="link">
								Open the Monitoring console
							</a>
							.
						</>
					) : null}
				</Prose>
			</Panel>
		);
	}
	const f = report.figures;
	return (
		<Panel title="Health" note={stale ?? healthHeadline(report)}>
			<Facts
				items={[
					["Up, last day", percent(f.availability)],
					["5xx, last hour", percent(f.error_share)],
					[
						"p95 latency, last hour",
						f.p95_latency_ms === null || f.p95_latency_ms === undefined
							? "no data"
							: `${whole(Math.round(f.p95_latency_ms))} ms`,
					],
					["Active instances now", instancesOf(report)],
				]}
			/>
			{links ? (
				<Prose>
					<a href={links.monitoring} className="link">
						The full dashboard
					</a>
				</Prose>
			) : null}
		</Panel>
	);
}
