/**
 * Capacity and cost (docs/backoffice.md § The pages, Capacity): what the
 * platform takes up and what the coach costs, from what the API serves —
 * each collection's size as it stands, the database's size a day as the job
 * runner kept it with the pace the API read off it, the cluster's
 * connections, and the coach's cost a day and model for the last 31 days —
 * with the instance count from live health and links to where the rest is
 * kept. Until two sizes are kept there is no pace, and the page says when
 * there will be one rather than drawing a line.
 */

import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useRef, useState } from "react";
import { get } from "@/shared/api/client";
import type { CapacityReport } from "@/shared/api/schema";
import {
	cacheSentence,
	coachMonth,
	dailyCostByFamily,
	growthCell,
	longDay,
	moved,
	sizeChart,
	sizeHeadline,
	sparkPoints,
} from "@/shared/lib/capacity";
import { useConsole } from "@/shared/lib/console";
import { dollars, formatBytes, whole } from "@/shared/lib/format";
import { instancesOf, useHealth } from "@/shared/lib/health";
import {
	day,
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

/** A tile's sparkline: the shape of the figure above it, named in words. */
function Spark({ values, said }: { values: number[]; said: string }) {
	return (
		<svg viewBox="0 0 84 24" width="84" height="24" role="img" aria-label={said}>
			<polyline
				points={sparkPoints(values, 84, 24)}
				fill="none"
				stroke="var(--data-blue)"
				strokeWidth="2"
				strokeLinecap="round"
				strokeLinejoin="round"
			/>
		</svg>
	);
}

function DatabaseTile({ report, stored }: { report: CapacityReport; stored: number }) {
	const sizes = report.sizes ?? [];
	const indexed = report.collections.reduce((sum, c) => sum + c.index_bytes, 0);
	const first = sizes[0];
	return (
		<Tile label="Database" value={formatBytes(stored)}>
			{sizes.length > 1 && first ? (
				<Spark
					values={sizes.map((s) => s.storage_bytes)}
					said={`The database's size a day since ${longDay(first.day)}`}
				/>
			) : null}
			{report.growth ? <p className={caption}>{moved(report.growth)}</p> : null}
			<p className={caption}>Plus {formatBytes(indexed)} in indexes.</p>
		</Tile>
	);
}

function ConnectionsTile({ connections }: { connections: CapacityReport["connections"] }) {
	return (
		<Tile label="Database connections" value={connections ? whole(connections.current) : "—"}>
			{connections ? (
				<>
					<Meter
						value={connections.current}
						max={connections.allowed}
						label={`Database connections: ${whole(connections.current)} of ${whole(connections.allowed)} allowed`}
					/>
					<p className={caption}>Of {whole(connections.allowed)} allowed.</p>
				</>
			) : (
				<p className={caption}>
					The cluster didn't say. Its connections need the serverStatus action on the operator's
					database user.
				</p>
			)}
		</Tile>
	);
}

function CoachTile({ report, now }: { report: CapacityReport; now: Date }) {
	const month = coachMonth(report.coach_cost, now);
	return (
		<Tile label="Coach this month" value={dollars(month.spent)}>
			{month.running.length > 1 ? (
				<Spark
					values={month.running}
					said={`Spent ${dollars(month.spent)} so far this month, day by day`}
				/>
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

// The plot's own units; it is stretched to the panel's width at a fixed
// height, so its text and dots are HTML laid over it rather than SVG that
// would shrink with a narrow window.
const CHART_W = 760;
const CHART_H = 150;

const at = (x: number) => `${(x / CHART_W) * 100}%`;

/**
 * The database's size a day, and the pace carried forward from the newest,
 * dashed. Hovering names the nearest day kept; the table under it holds
 * every size, for the keyboard and for anyone who wants the number.
 */
function SizePanel({ report }: { report: CapacityReport }) {
	const sizes = report.sizes ?? [];
	const chart = sizeChart(sizes, report.growth, CHART_W, CHART_H);
	const plot = useRef<HTMLDivElement>(null);
	const [hovered, setHovered] = useState<number | null>(null);
	const first = sizes[0];
	const last = sizes[sizes.length - 1];
	if (!chart || !first || !last) {
		return (
			<Panel raised title="Database size">
				<Prose>
					{first
						? `One size is kept so far, ${formatBytes(first.storage_bytes)} on ${longDay(first.day)}. The line starts when a second is kept.`
						: "No size is kept yet. The job runner keeps one a day from its next run, and the line starts once there are two."}
				</Prose>
			</Panel>
		);
	}
	const pace = report.growth?.bytes_a_month;
	const said = `The database went from ${formatBytes(first.storage_bytes)} on ${longDay(first.day)} to ${formatBytes(last.storage_bytes)} on ${longDay(last.day)}${
		chart.end && pace !== undefined
			? `, and at about ${formatBytes(Math.abs(pace))} a month ${pace < 0 ? "less" : "more"} would take up ${formatBytes(chart.end.bytes)} by ${longDay(chart.end.day)}`
			: ""
	}.`;
	const shown = hovered === null ? null : chart.points[hovered];
	const pick = (clientX: number) => {
		const box = plot.current?.getBoundingClientRect();
		if (!box || box.width === 0) return;
		const x = ((clientX - box.left) / box.width) * CHART_W;
		let best = 0;
		chart.points.forEach((p, i) => {
			if (Math.abs(p.x - x) < Math.abs((chart.points[best]?.x ?? 0) - x)) best = i;
		});
		setHovered(best);
	};
	const nowLeft = (chart.now.x / CHART_W) * 100;
	return (
		<Panel
			raised
			title="Database size"
			note="A size a day as the job runner kept it, and the current pace carried forward, dashed."
		>
			<figure className="px-6 pb-5">
				{/* biome-ignore lint/a11y/noStaticElementInteractions: the hover only names a day; the table below carries the same figures */}
				<div
					ref={plot}
					className="relative mt-8 h-36 sm:h-48"
					onMouseMove={(e) => pick(e.clientX)}
					onMouseLeave={() => setHovered(null)}
				>
					<svg
						viewBox={`0 0 ${CHART_W} ${CHART_H}`}
						preserveAspectRatio="none"
						className="absolute inset-0 h-full w-full overflow-visible"
						role="img"
						aria-label={said}
					>
						<line
							x1="0"
							x2={CHART_W}
							y1={CHART_H}
							y2={CHART_H}
							stroke="var(--hairline)"
							strokeWidth="1"
							vectorEffect="non-scaling-stroke"
						/>
						{chart.ahead ? (
							<polyline
								points={chart.ahead}
								fill="none"
								stroke="var(--data-blue)"
								strokeWidth="2"
								strokeDasharray="6 6"
								strokeLinecap="round"
								vectorEffect="non-scaling-stroke"
							/>
						) : null}
						<polyline
							points={chart.actual}
							fill="none"
							stroke="var(--data-blue)"
							strokeWidth="2"
							strokeLinecap="round"
							strokeLinejoin="round"
							vectorEffect="non-scaling-stroke"
						/>
						{shown ? (
							<line
								x1={shown.x}
								x2={shown.x}
								y1="0"
								y2={CHART_H}
								stroke="var(--ink-muted)"
								strokeWidth="1"
								vectorEffect="non-scaling-stroke"
							/>
						) : null}
					</svg>
					<span
						aria-hidden="true"
						className="absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--data-blue)] ring-2 ring-panel-solid"
						style={{ left: at(chart.now.x), top: `${(chart.now.y / CHART_H) * 100}%` }}
					/>
					<span
						aria-hidden="true"
						className={`absolute -translate-y-full pb-2 font-heading text-[14px] whitespace-nowrap ${
							nowLeft > 70 ? "-translate-x-full" : nowLeft < 30 ? "" : "-translate-x-1/2"
						}`}
						style={{ left: at(chart.now.x), top: `${(chart.now.y / CHART_H) * 100}%` }}
					>
						{formatBytes(last.storage_bytes)} on {longDay(last.day)}
					</span>
					{shown ? (
						<div
							className="pointer-events-none absolute -top-8 -translate-x-1/2 rounded-full bg-ink px-2.5 py-0.5 text-[12px] whitespace-nowrap text-panel-solid"
							style={{ left: `${Math.min(85, Math.max(15, (shown.x / CHART_W) * 100))}%` }}
						>
							{longDay(shown.day)}: {formatBytes(shown.bytes)}
						</div>
					) : null}
				</div>
				<figcaption
					aria-hidden="true"
					className="relative mt-1.5 h-5 font-heading text-[12px] text-ink-muted"
				>
					{chart.labels.map((l) => (
						<span
							key={`${l.anchor}-${l.text}`}
							className={`absolute whitespace-nowrap ${
								l.anchor === "end"
									? "-translate-x-full"
									: l.anchor === "middle"
										? "-translate-x-1/2"
										: ""
							}`}
							style={{ left: at(l.x) }}
						>
							{l.text}
						</span>
					))}
				</figcaption>
				<details className="mt-2 text-[14px]">
					<summary className="link flex h-10 w-fit cursor-pointer items-center">
						See every day
					</summary>
					<div className="-mx-6 mt-1 max-h-72 overflow-y-auto">
						<Table
							head={[day("Day"), figure("Size")]}
							rows={[...sizes].reverse().map((s) => [s.day, formatBytes(s.storage_bytes)])}
							empty={null}
						/>
					</div>
				</details>
			</figure>
		</Panel>
	);
}

/**
 * The coach's cost a day, stacked by model family in a fixed order and
 * colour, with a legend; hovering a day names its parts, and the table under
 * it holds every figure.
 */
function CoachBars({ report, days, now }: { report: CapacityReport; days: number; now: Date }) {
	const { families, days: bars } = dailyCostByFamily(report.coach_cost, days, now);
	const [hovered, setHovered] = useState<number | null>(null);
	const peak = Math.max(...bars.map((d) => d.total), 0.01);
	const shown = hovered === null ? null : bars[hovered];
	const dated = bars.filter((d) => d.total > 0).reverse();
	const parts = (d: { parts: number[] }) =>
		families.map((f, i) => `${f.family} ${dollars(d.parts[i] ?? 0)}`).join(", ");
	return (
		<figure className="px-6 pb-2">
			{families.length > 0 ? (
				<ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px]" aria-label="Models">
					{families.map((f) => (
						<li key={f.family} className="inline-flex items-center gap-1.5">
							<span
								aria-hidden="true"
								className="size-2.5 rounded-full"
								style={{ background: f.colour }}
							/>
							{f.family}
						</li>
					))}
				</ul>
			) : null}
			<div
				role="img"
				aria-label={`The coach's cost a day over the last ${days} days, by model.`}
				className="relative flex h-28 items-end gap-0.5"
				onMouseLeave={() => setHovered(null)}
			>
				{bars.map((d, i) => (
					// biome-ignore lint/a11y/noStaticElementInteractions: the hover only names a bar; the table below carries the same figures
					<div
						key={d.day}
						className="flex h-full min-w-0 flex-1 items-end"
						onMouseEnter={() => setHovered(i)}
					>
						{d.total > 0 ? (
							<div
								className={`flex w-full flex-col-reverse gap-[2px] overflow-hidden rounded-t-[4px] ${hovered === i ? "opacity-80" : ""}`}
								style={{ height: `${(d.total / peak) * 100}%` }}
							>
								{families.map((f, j) =>
									(d.parts[j] ?? 0) > 0 ? (
										<div
											key={f.family}
											className="min-h-[2px]"
											style={{ flex: `${d.parts[j]} 1 0`, background: f.colour }}
										/>
									) : null,
								)}
							</div>
						) : (
							<div className="h-[2px] w-full bg-track" />
						)}
					</div>
				))}
				{shown && hovered !== null ? (
					<div
						className="pointer-events-none absolute -top-2 -translate-x-1/2 rounded-full bg-ink px-2.5 py-0.5 text-[12px] whitespace-nowrap text-panel-solid"
						style={{
							left: `${Math.min(85, Math.max(15, ((hovered + 0.5) / bars.length) * 100))}%`,
						}}
					>
						{shown.day}: {dollars(shown.total)}
						{shown.total > 0 && families.length > 1 ? ` — ${parts(shown)}` : ""}
					</div>
				) : null}
			</div>
			<figcaption className="mt-1.5 flex justify-between font-heading text-[12px] text-ink-muted">
				<span>{bars[0]?.day}</span>
				<span>{bars[bars.length - 1]?.day}</span>
			</figcaption>
			{dated.length > 0 ? (
				<details className="mt-2 text-[14px]">
					<summary className="link flex h-10 w-fit cursor-pointer items-center">
						See every day
					</summary>
					<div className="-mx-6 mt-1 max-h-72 overflow-y-auto">
						<Table
							head={[day("Day"), ...families.map((f) => figure(f.family)), figure("Total")]}
							rows={dated.map((d) => [
								d.day,
								...families.map((_, i) => dollars(d.parts[i] ?? 0)),
								dollars(d.total),
							])}
							empty={null}
						/>
					</div>
				</details>
			) : null}
		</figure>
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
	const said = cacheSentence(data.coach_cost, days, now);
	const { title, lead } = sizeHeadline(data, now);
	const paced = Boolean(data.growth);

	return (
		<Page title={title} lead={lead}>
			<section
				aria-label="Where things stand"
				className="grid gap-[18px] sm:grid-cols-2 xl:grid-cols-4"
			>
				<DatabaseTile report={data} stored={stored} />
				<CoachTile report={data} now={now} />
				<InstancesTile />
				<ConnectionsTile connections={data.connections} />
			</section>

			<SizePanel report={data} />

			<Panel title="Coach cost" note={`Dollars a day, the last ${days} days, UTC.`}>
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
				<CoachBars report={data} days={days} now={now} />
				<Prose>{said}</Prose>
			</Panel>

			<div className="grid grid-cols-[minmax(0,1fr)] items-start gap-[18px] lg:grid-cols-[minmax(0,1fr)_300px]">
				<Panel title="What takes up the room" note="Largest first.">
					<Table
						head={[
							"Collection",
							figure("Size"),
							figure("Documents"),
							figure("Indexes"),
							figure("Growth a month"),
						]}
						rows={collections.map((c) => [
							<code key="n">{c.name}</code>,
							formatBytes(c.storage_bytes),
							whole(c.documents),
							formatBytes(c.index_bytes),
							growthCell(c, paced),
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
