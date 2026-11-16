/**
 * Hours logged (docs/backoffice.md § The pages, decided 2026-11-16): how
 * much time the product has tracked all told, this month, and over time —
 * by day, week or month, over a span the reader picks — with how many
 * sessions made it and how many accounts logged any. Across everyone, in
 * UTC, by the day each session started on, as the API buckets a day; a
 * running timer is not yet hours. Nothing here says who logged what.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { get } from "@/shared/api/client";
import type { HoursReport, HoursUnit } from "@/shared/api/schema";
import { whole } from "@/shared/lib/format";
import {
	everyBucket,
	hoursHeadline,
	hoursOf,
	hoursSentence,
	SPANS,
	UNITS,
} from "@/shared/lib/usage";
import { DayBars, Failed, Loading, Page, Panel, Prose } from "@/shared/ui";

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
	return (
		<Panel className="flex flex-col gap-1.5 px-5 py-4">
			<p className="text-[13px] text-ink-muted">{label}</p>
			<p className="font-heading text-[28px] leading-none font-extrabold">{value}</p>
			{note ? <p className="text-[13px] text-ink-muted">{note}</p> : null}
		</Panel>
	);
}

function Choice<T extends string | number>({
	label,
	options,
	value,
	onChange,
	name,
}: {
	label: string;
	options: ReadonlyArray<{ id: T; label: string }>;
	value: T;
	onChange: (id: T) => void;
	name: string;
}) {
	return (
		<fieldset className="flex flex-wrap gap-1">
			<legend className="sr-only">{label}</legend>
			{options.map((o) => (
				<button
					key={`${name}-${o.id}`}
					type="button"
					aria-pressed={o.id === value}
					onClick={() => onChange(o.id)}
					className={`h-9 rounded-full px-3.5 text-[14px] ${
						o.id === value ? "bg-wash-strong font-bold" : "hover:bg-wash"
					}`}
				>
					{o.label}
				</button>
			))}
		</fieldset>
	);
}

export function Hours() {
	const [unit, setUnit] = useState<HoursUnit>("day");
	const [periods, setPeriods] = useState<number>(SPANS.day[0]);
	const { data, error, refetch } = useQuery({
		queryKey: ["hours", unit, periods],
		queryFn: () => get<HoursReport>(`/api/operator/hours?unit=${unit}&periods=${periods}`),
		placeholderData: (previous) => previous,
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const spec = UNITS.find((u) => u.id === unit) ?? UNITS[0];
	const drawn = everyBucket(data.buckets, data.since, data.unit, data.periods);
	const said = hoursSentence(drawn, data.unit);
	const pickUnit = (next: HoursUnit) => {
		setUnit(next);
		setPeriods(SPANS[next][0]);
	};
	return (
		<Page
			title={hoursHeadline(data.total_hours, data.accounts_last_30d)}
			lead="What the product has tracked, across everyone, in UTC. A session counts on the day it started, once it has ended; a running timer is in no figure here."
		>
			<section className="grid gap-[18px] sm:grid-cols-2 lg:grid-cols-4">
				<Tile label="Hours logged, all told" value={hoursOf(data.total_hours)} />
				<Tile label="This month" value={hoursOf(data.this_month_hours)} note="UTC, to now" />
				<Tile label="Sessions, all told" value={whole(data.total_sessions)} />
				<Tile
					label="People who logged any"
					value={whole(data.accounts_ever)}
					note={`${whole(data.accounts_last_30d)} in the last 30 days`}
				/>
			</section>
			<Panel
				raised
				title="Hours over time"
				note={`Hours a ${spec.one}, the last ${data.periods} ${data.periods === 1 ? spec.one : spec.many}, UTC.`}
			>
				<div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-6 pb-2">
					<Choice label="Bucket" name="unit" options={UNITS} value={unit} onChange={pickUnit} />
					<Choice
						label="Span"
						name="span"
						options={SPANS[unit].map((n) => ({ id: n, label: `${n} ${spec.many}` }))}
						value={periods}
						onChange={setPeriods}
					/>
				</div>
				<DayBars days={drawn} said={said} unit="Hours" show={hoursOf} />
				<Prose>{said}</Prose>
			</Panel>
		</Page>
	);
}
