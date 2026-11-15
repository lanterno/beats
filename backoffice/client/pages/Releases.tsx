/**
 * Releases (docs/backoffice.md § The pages, Releases): when something breaks,
 * what shipped just before it. The API's builds newest first, the commit its
 * serving revision runs, and the web app's live commit. No control here moves
 * traffic: a bad release is reverted on main, which the runbook says.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { FreezeState, HeldBuild, ReleasesReport } from "@/shared/api/schema";
import { minuteOf } from "@/shared/lib/format";
import {
	buildLabel,
	commitUrl,
	isBad,
	releasesHeadline,
	rerunAdvice,
	short,
	unanswered,
} from "@/shared/lib/releases";
import {
	buttonClass,
	Chip,
	day,
	Empty,
	Facts,
	Failed,
	Loading,
	Page,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";

/** The build to re-run, and where: Cloud Build's page for it has the re-run. */
function Rerun({ rerun, frozen }: { rerun: HeldBuild | null | undefined; frozen: boolean }) {
	const advice = rerunAdvice(rerun, frozen);
	if (!advice) return null;
	return (
		<span className="text-[13px] text-ink-muted">
			{advice}
			{rerun?.log_url ? (
				<>
					{" "}
					<a href={rerun.log_url} className="link">
						Open the build
					</a>
				</>
			) : null}
		</span>
	);
}

/** The deploy freeze: whether it holds, and the two acts, each through its review. */
function FreezePanel({ rerun }: { rerun: HeldBuild | null | undefined }) {
	const freeze = useQuery({
		queryKey: ["deploy-freeze"],
		queryFn: () => get<FreezeState>("/api/operator/deploy-freeze"),
	});
	if (freeze.error) {
		return (
			<Panel title="Deploy freeze">
				<Failed bare error={freeze.error} onRetry={() => freeze.refetch()} />
			</Panel>
		);
	}
	if (!freeze.data) return null;
	const f = freeze.data;
	if (!f.available) {
		return (
			<Panel title="Deploy freeze">
				<Prose>
					This deployment has no freeze bucket, so its builds cannot be held back from here.
				</Prose>
			</Panel>
		);
	}
	if (f.frozen === null) {
		return (
			<Panel title="Deploy freeze">
				<div className="flex flex-wrap items-center justify-between gap-4 px-6 pb-5">
					<p className="min-w-0 flex-1 text-[15px] leading-relaxed">
						Whether API deploys are frozen is unknown: the freeze's bucket did not answer. A build
						that cannot read it stops rather than deploy.
					</p>
					<button
						type="button"
						onClick={() => freeze.refetch()}
						className={buttonClass("secondary")}
					>
						Try again
					</button>
				</div>
			</Panel>
		);
	}
	return (
		<Panel
			raised={f.frozen}
			title="Deploy freeze"
			note={
				f.frozen
					? `API deploys are frozen until ${minuteOf(f.until)} UTC${f.reason ? ` — ${f.reason}` : ""}. The web app can still ship.`
					: "API deploys are shipping. Freezing holds back every API build until a time you set; the web app is not held."
			}
		>
			<div className="flex flex-wrap items-center gap-3 px-6 pb-5">
				{f.frozen ? (
					<Link to="/review/deploy.unfreeze/api" className={buttonClass("primary")}>
						Lift the freeze
					</Link>
				) : (
					<Link to="/review/deploy.freeze/api" className={buttonClass("secondary")}>
						Freeze the API's deploys
					</Link>
				)}
				<Rerun rerun={rerun} frozen={f.frozen} />
			</div>
		</Panel>
	);
}

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
				note="Newest first. The live one is the commit the API's serving revision runs, so a revision that failed to start leaves the one before it live. One the deploy freeze held back is red in Cloud Build and was never deployed."
			>
				<Table
					head={[day("Started"), "Commit", "What", "Build", ""]}
					rows={r.builds.map((b) => [
						minuteOf(b.created_at),
						sha(b.sha),
						b.subject ?? "—",
						<Chip key="s" tone={isBad(b) ? "owed" : b.status === "SUCCESS" ? "good" : "quiet"}>
							{buildLabel(b)}
						</Chip>,
						b.live ? (
							<Chip key="l">Live</Chip>
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
			<FreezePanel rerun={r.rerun} />
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
