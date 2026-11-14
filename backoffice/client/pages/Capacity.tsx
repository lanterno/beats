/**
 * Capacity and cost (docs/backoffice.md § The pages, Capacity): what the
 * platform takes up and what the coach costs, from what the API serves —
 * each collection's size as it stands and the coach's cost a day and model
 * for the last 31 days — with the instance count from live health and links
 * to where the rest is kept. Nothing keeps the database's size over time, so
 * there is no growth to chart or carry forward; the one pace is the coach's.
 */

import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { get } from "@/shared/api/client";
import type { CapacityReport } from "@/shared/api/schema";
import { cacheSentence, coachMonth, dailyCost, sparkPoints } from "@/shared/lib/capacity";
import { useConsole } from "@/shared/lib/console";
import { dollars, formatBytes, whole } from "@/shared/lib/format";
import { instancesOf, useHealth } from "@/shared/lib/health";
import {
	DayBars,
	Empty,
	Facts,
	Failed,
	figure,
	Loading,
	Meter,
	Page,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";

const RANGES = [7, 30] as const;

/** One figure at the top of the page, with what it is measured against. */
function Tile({ label, value, children }: { label: string; value: string; children: ReactNode }) {
	return (
		<Panel className="flex flex-col gap-1.5 px-5 py-4">
			<p className="text-[13px] text-ink-muted">{label}</p>
			<p className="font-heading text-[28px] leading-none font-extrabold">{value}</p>
			{children}
		</Panel>
	);
}

const caption = "text-[13px] text-ink-muted";

function CoachTile({ report, now }: { report: CapacityReport; now: Date }) {
	const month = coachMonth(report.coach_cost, now);
	return (
		<Tile label="Coach this month" value={dollars(month.spent)}>
			{month.running.length > 1 ? (
				<svg
					viewBox="0 0 84 24"
					width="84"
					height="24"
					role="img"
					aria-label={`Spent ${dollars(month.spent)} so far this month, day by day`}
				>
					<polyline
						points={sparkPoints(month.running, 84, 24)}
						fill="none"
						stroke="var(--data-blue)"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			) : null}
			<p className={caption}>
				{month.heading === null
					? "Too early in the month to say where it's heading."
					: `Heading for about ${dollars(month.heading)}, at the pace so far.`}
			</p>
		</Tile>
	);
}

function InstancesTile() {
	const health = useHealth();
	const report = health.data;
	const now = report?.figures?.instances;
	const max = report?.max_instances;
	return (
		<Tile
			label="Active instances now"
			value={report && now !== null && now !== undefined ? String(Math.round(now)) : "—"}
		>
			{report && now !== null && now !== undefined && max ? (
				<>
					<Meter
						value={Math.round(now)}
						max={max}
						label={`Active instances: ${instancesOf(report)}`}
					/>
					<p className={caption}>Of a ceiling of {max}, on the busiest revision.</p>
				</>
			) : (
				<p className={caption}>
					{health.error || report?.state === "unavailable"
						? "Live health is unavailable here."
						: report
							? "No data from Monitoring yet."
							: "Reading live health…"}
				</p>
			)}
		</Tile>
	);
}

/** Refused writes by route, from live health: the limits' effect, not who was refused. */
function RefusedPanel() {
	const health = useHealth();
	const routes = health.data?.figures?.refused_writes;
	return (
		<Panel
			title="Writes refused, last day"
			note="By route. Which accounts is a log query, on Today."
		>
			{health.error ? (
				<Failed bare error={health.error} onRetry={() => health.refetch()} />
			) : !health.data ? (
				<Loading />
			) : !health.data.figures ? (
				<Prose>Live health is unavailable here.</Prose>
			) : (
				<Table
					head={["Route", figure("Refused")]}
					rows={(routes ?? []).map((r) => [<code key="r">{r.route}</code>, whole(r.value)])}
					empty={<Empty title="No write was refused by a limit." />}
				/>
			)}
		</Panel>
	);
}

export function Capacity() {
	const links = useConsole();
	const [days, setDays] = useState<(typeof RANGES)[number]>(30);
	const { data, error, refetch } = useQuery({
		queryKey: ["capacity"],
		queryFn: () => get<CapacityReport>("/api/operator/capacity"),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const now = new Date();
	const collections = [...data.collections].sort((a, b) => b.storage_bytes - a.storage_bytes);
	const stored = collections.reduce((sum, c) => sum + c.storage_bytes, 0);
	const indexed = collections.reduce((sum, c) => sum + c.index_bytes, 0);
	const largest = collections[0];
	const said = cacheSentence(data.coach_cost, days, now);

	return (
		<Page
			title={`The database takes up ${formatBytes(stored)}.`}
			lead={
				largest
					? `${largest.name} is the largest of ${collections.length} collections, at ${formatBytes(largest.storage_bytes)}. Nothing keeps the size over time, so this is where it stands, not a pace.`
					: "The database has no collections yet."
			}
		>
			<section aria-label="Where things stand" className="grid gap-[18px] sm:grid-cols-3">
				<Tile label="Database" value={formatBytes(stored)}>
					<p className={caption}>Plus {formatBytes(indexed)} in indexes.</p>
				</Tile>
				<CoachTile report={data} now={now} />
				<InstancesTile />
			</section>

			<Panel raised title="Coach cost" note={`Dollars a day, the last ${days} days, UTC.`}>
				<fieldset className="flex gap-1 px-6 pb-2">
					<legend className="sr-only">Choose a range</legend>
					{RANGES.map((range) => (
						<button
							key={range}
							type="button"
							aria-pressed={range === days}
							onClick={() => setDays(range)}
							className={`h-9 rounded-full px-3.5 text-[14px] ${
								range === days ? "bg-wash-strong font-bold" : "hover:bg-wash"
							}`}
						>
							{range} days
						</button>
					))}
				</fieldset>
				<DayBars
					days={dailyCost(data.coach_cost, days, now)}
					said={`The coach's cost a day over the last ${days} days. ${said}`}
					unit="Cost"
					show={dollars}
				/>
				<Prose>{said}</Prose>
			</Panel>

			<div className="grid items-start gap-[18px] lg:grid-cols-[minmax(0,1fr)_300px]">
				<Panel title="What takes up the room" note="Largest first.">
					<Table
						head={["Collection", figure("Size"), figure("Documents"), figure("Indexes")]}
						rows={collections.map((c) => [
							<code key="n">{c.name}</code>,
							formatBytes(c.storage_bytes),
							whole(c.documents),
							formatBytes(c.index_bytes),
						])}
						empty={<Empty title="No collections yet." />}
					/>
				</Panel>
				<div className="flex flex-col gap-[18px]">
					<RefusedPanel />
					<Panel title="Restores" note="Counted in the logs, by size only; nothing stores them.">
						{links ? (
							<Facts
								items={[
									[
										"Their sizes",
										<a key="s" href={links.apiMetric("import_bytes")} className="link">
											Over time
										</a>,
									],
									[
										"Each one",
										<a key="e" href={links.apiLog("IMPORT_RECEIVED", 30)} className="link">
											The last 30 days
										</a>,
									],
								]}
							/>
						) : (
							<Prose>Cloud Monitoring and the API's log have them, on Google Cloud.</Prose>
						)}
					</Panel>
					<Panel title="Look closer">
						<ul className="flex flex-col gap-1 px-6 pb-5 text-[14px]">
							{links ? (
								<>
									<li>
										<a href={links.monitoring} className="link">
											The API dashboard in Cloud Monitoring
										</a>
									</li>
									<li>
										<a href={links.cloudRun} className="link">
											The API's revisions in Cloud Run
										</a>
									</li>
									<li>
										<a href={links.billing} className="link">
											Billing in Google Cloud
										</a>
									</li>
								</>
							) : null}
							<li>
								<a href="https://cloud.mongodb.com/" className="link">
									The cluster in MongoDB Atlas
								</a>
							</li>
						</ul>
					</Panel>
				</div>
			</div>
		</Page>
	);
}
