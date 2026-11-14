/**
 * Releases (docs/backoffice.md § The pages, Releases): when something breaks,
 * what shipped just before it. The API's builds newest first, the commit it
 * was deployed with, and the web app's live commit. No control here moves
 * traffic: a bad release is reverted on main, which the runbook says.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { ReleasesReport } from "@/shared/api/schema";
import { minuteOf } from "@/shared/lib/format";
import {
	commitUrl,
	isBad,
	releasesHeadline,
	short,
	statusLabel,
	unanswered,
} from "@/shared/lib/releases";
import { Chip, day, Empty, Facts, Failed, Loading, Page, Panel, Prose, Table } from "@/shared/ui";

export function Releases() {
	const releases = useQuery({
		queryKey: ["releases"],
		queryFn: () => get<ReleasesReport>("/api/operator/releases"),
	});
	if (releases.error) return <Failed error={releases.error} onRetry={() => releases.refetch()} />;
	if (!releases.data) return <Loading />;
	const r = releases.data;
	const missing = unanswered(r);
	const sha = (value: string | null | undefined) =>
		value ? (
			<a href={commitUrl(r.repository, value)} className="link">
				<code className="text-[13px]">{short(value)}</code>
			</a>
		) : (
			"unknown"
		);

	return (
		<Page title="Releases" lead={`${releasesHeadline(r)} Times are UTC.`}>
			{missing ? (
				<Panel>
					<Prose>{missing}</Prose>
				</Panel>
			) : null}
			<Panel
				raised
				title="API builds"
				note="Newest first. The live one is what the API was deployed with: a revision that failed to start would leave the previous one serving."
			>
				<Table
					head={[day("Started"), "Commit", "What", "Build", ""]}
					rows={r.builds.map((b) => [
						minuteOf(b.created_at),
						sha(b.sha),
						b.subject ?? "—",
						<Chip key="s" tone={isBad(b) ? "owed" : b.status === "SUCCESS" ? "good" : "quiet"}>
							{statusLabel(b.status)}
						</Chip>,
						b.live ? (
							<Chip key="l">Live, as deployed</Chip>
						) : isBad(b) ? (
							<Link key="r" to="/runbooks/bad-release" className="link">
								What to do
							</Link>
						) : b.log_url ? (
							<a key="g" href={b.log_url} className="link">
								Log
							</a>
						) : null,
					])}
					empty={
						<Empty title="No builds to show.">Cloud Build answers only on Google Cloud.</Empty>
					}
				/>
			</Panel>
			<Panel title="The web app">
				<Facts
					items={[
						["Live commit", sha(r.web_commit)],
						["What", r.web_subject ?? "—"],
						[
							"Ships from",
							"The deploy job in .github/workflows/ui.yml, on every push touching ui/",
						],
					]}
				/>
			</Panel>
			<Prose>
				A bad release is reverted on main, and the revert deploys like any other commit.{" "}
				<Link to="/runbooks/bad-release" className="link">
					The runbook
				</Link>
				.
			</Prose>
		</Page>
	);
}
