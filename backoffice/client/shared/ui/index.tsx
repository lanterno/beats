/**
 * What every page is made of, in the app's own look: a page header on the
 * sky, cloud-white panels, and inside them tables and fact lists. The tables
 * are tighter than the app's usual spacing on purpose: these pages are lists
 * to scan.
 */

import { type InputHTMLAttributes, type ReactNode, useState } from "react";
import { Link } from "react-router";
import { plainMessage } from "@/shared/lib/errors";
import { ArrowLeftIcon } from "./icons";

export function Page({
	title,
	lead,
	back,
	aside,
	children,
}: {
	title: string;
	/** The page's point, said in a sentence before anything is shown. */
	lead?: ReactNode;
	back?: { to: string; label: string };
	aside?: ReactNode;
	children: ReactNode;
}) {
	return (
		<>
			<header className="mb-6">
				{back ? (
					<Link
						to={back.to}
						className="link -mt-2 mb-1 inline-flex h-10 items-center gap-1.5 text-[14px]"
					>
						<ArrowLeftIcon className="size-4" />
						{back.label}
					</Link>
				) : null}
				<div className="flex items-start justify-between gap-6">
					<div className="min-w-0">
						<h1 className="font-heading text-[34px] leading-tight font-extrabold break-words">
							{title}
						</h1>
						{lead ? (
							<p className="mt-1.5 max-w-[62ch] text-[16px] leading-relaxed">{lead}</p>
						) : null}
					</div>
					{aside}
				</div>
			</header>
			<div className="flex flex-col gap-[18px]">{children}</div>
		</>
	);
}

/** Two panels side by side, one under the other on a narrow window. */
export function Pair({ children }: { children: ReactNode }) {
	return <div className="grid gap-[18px] md:grid-cols-2">{children}</div>;
}

export function Panel({
	title,
	note,
	raised = false,
	danger = false,
	className = "",
	children,
}: {
	title?: string;
	note?: ReactNode;
	/** The one panel a screen is about. */
	raised?: boolean;
	/** Its acts are destructive. */
	danger?: boolean;
	className?: string;
	children: ReactNode;
}) {
	const shadow = raised ? "shadow-[var(--shadow-raised)]" : "shadow-[var(--shadow-hairline)]";
	const outline = danger ? "ring-1 ring-persimmon ring-inset" : "";
	return (
		<section className={`rounded-[var(--radius-panel)] bg-panel ${shadow} ${outline} ${className}`}>
			{title ? (
				<header className="px-6 pt-5 pb-2">
					<h2 className="font-heading text-[18px] font-bold">{title}</h2>
					{note ? (
						<p className="mt-0.5 text-[14px] leading-relaxed text-ink-muted">{note}</p>
					) : null}
				</header>
			) : null}
			{children}
		</section>
	);
}

/** A sentence or two inside a panel. */
export function Prose({ children }: { children: ReactNode }) {
	return <p className="px-6 pb-5 text-[15px] leading-relaxed">{children}</p>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
	return (
		<div className="px-6 pt-2 pb-5 text-center">
			<p className="text-[15px] font-bold">{title}</p>
			{children ? <p className="text-[14px] text-ink-muted">{children}</p> : null}
		</div>
	);
}

type ColumnKind = "text" | "figure" | "day";
export type Column = string | { label: string; kind: ColumnKind };

/** A column of amounts: right-aligned, so the digits line up. */
export const figure = (label: string): Column => ({ label, kind: "figure" });
/** A column of dates or times. */
export const day = (label: string): Column => ({ label, kind: "day" });

const COLUMN: Record<ColumnKind, string> = {
	text: "",
	figure: "text-right font-heading",
	day: "font-heading text-[13px] whitespace-nowrap",
};

const kindOf = (column: Column): ColumnKind => (typeof column === "string" ? "text" : column.kind);
const labelOf = (column: Column): string => (typeof column === "string" ? column : column.label);

export function Table({
	head,
	rows,
	empty,
}: {
	head: Column[];
	rows: ReactNode[][];
	/** Why it is empty and what fills it. */
	empty: ReactNode;
}) {
	if (rows.length === 0) return <>{empty}</>;
	return (
		<div className="overflow-x-auto pb-3">
			<table className="w-full text-[14px]">
				<thead>
					<tr className="text-left text-[13px] text-ink-muted">
						{head.map((column) => (
							<th
								key={labelOf(column)}
								scope="col"
								className={`px-2.5 py-1.5 font-medium first:pl-6 last:pr-6 ${kindOf(column) === "figure" ? "text-right" : ""}`}
							>
								{labelOf(column)}
							</th>
						))}
					</tr>
				</thead>
				<tbody>
					{rows.map((cells, i) => (
						// biome-ignore lint/suspicious/noArrayIndexKey: rows are read-only renderings of API lists with no stable id of their own
						<tr key={i} className="border-t border-hairline hover:bg-wash">
							{cells.map((cell, j) => (
								<td
									// biome-ignore lint/suspicious/noArrayIndexKey: a cell's column is its identity
									key={j}
									className={`px-2.5 py-[7px] align-middle first:pl-6 last:pr-6 ${COLUMN[kindOf(head[j] ?? "")]}`}
								>
									{cell}
								</td>
							))}
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}

/** Rows of a label and its value, parted by hairlines. */
export function Facts({ items }: { items: Array<[string, ReactNode]> }) {
	return (
		<dl className="px-6 pb-3">
			{items.map(([label, value]) => (
				<div
					key={label}
					className="flex items-baseline justify-between gap-6 border-t border-hairline py-[7px] text-[14px]"
				>
					<dt className="shrink-0 text-ink-muted">{label}</dt>
					<dd className="min-w-0 text-right break-words">{value}</dd>
				</div>
			))}
		</dl>
	);
}

/** An id: real code, and read as one. */
export function Id({ children }: { children: ReactNode }) {
	return <code className="text-[13px]">{children}</code>;
}

const CHIP = {
	quiet: "bg-wash text-ink",
	good: "bg-leaf/15 text-leaf-ink",
	owed: "bg-persimmon/15 text-persimmon-ink",
} as const;

export function Chip({
	tone = "quiet",
	children,
}: {
	tone?: keyof typeof CHIP;
	children: ReactNode;
}) {
	return (
		<span
			className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[13px] font-medium whitespace-nowrap ${CHIP[tone]}`}
		>
			{children}
		</span>
	);
}

const BUTTON = {
	/** One to a screen. */
	primary: "bg-sun font-bold text-on-sun",
	secondary: "bg-wash font-medium text-ink hover:bg-wash-strong",
	/** Only ever for what cannot be taken back. */
	danger: "bg-persimmon-ink font-bold text-panel-solid",
} as const;

export function buttonClass(kind: keyof typeof BUTTON): string {
	return `inline-flex h-10 items-center justify-center rounded-full px-5 text-[14px] whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${BUTTON[kind]}`;
}

export function TextField({
	label,
	className = "",
	...input
}: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
	return (
		<label className={`flex flex-col gap-1 ${className}`}>
			<span className="text-[13px] text-ink-muted">{label}</span>
			<input
				{...input}
				className="h-10 w-full rounded-[var(--radius-tile)] bg-wash px-3.5 text-[14px] text-ink"
			/>
		</label>
	);
}

/** How much of a limit is gone. Past 80% it turns: the line the Attention
 * page counts an account near its cap at. */
export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
	const share = max > 0 ? Math.min(value / max, 1) : 0;
	return (
		// biome-ignore lint/a11y/useSemanticElements: <meter> cannot be drawn as a rounded bar across browsers
		<div
			role="meter"
			aria-label={label}
			aria-valuemin={0}
			aria-valuemax={max}
			aria-valuenow={value}
			className="h-2 rounded-full bg-track"
		>
			<div
				className={`h-full rounded-full ${share >= 0.8 ? "bg-persimmon" : "bg-data"}`}
				style={{ width: `${share * 100}%` }}
			/>
		</div>
	);
}

/**
 * One count a day, as a strip of bars, with `said` as its accessible name.
 * Hovering a bar names it; the table under it holds every figure, for the
 * keyboard and for anyone who wants the number rather than the shape.
 */
export function DayBars({
	days,
	said,
	unit = "Count",
	show = String,
}: {
	days: Array<{ day: string; value: number }>;
	said: string;
	/** What the figures are, for the table's column. */
	unit?: string;
	/** How one reads, where a bare number is not it. */
	show?: (value: number) => string;
}) {
	const [hovered, setHovered] = useState<number | null>(null);
	const peak = Math.max(...days.map((d) => d.value), 1);
	const shown = hovered === null ? null : days[hovered];
	const dated = days.filter((d) => d.value > 0).reverse();
	return (
		<figure className="px-6 pb-5">
			<div
				role="img"
				aria-label={said}
				className="relative flex h-24 items-end gap-0.5"
				onMouseLeave={() => setHovered(null)}
			>
				{days.map((d, i) => (
					// biome-ignore lint/a11y/noStaticElementInteractions: the hover only names a bar; the table below carries the same figures
					<div
						key={d.day}
						className="flex h-full min-w-0 flex-1 items-end"
						onMouseEnter={() => setHovered(i)}
					>
						<div
							className={`w-full rounded-t-[4px] ${d.value > 0 ? (hovered === i ? "bg-ink" : "bg-data") : "bg-track"}`}
							style={{ height: d.value > 0 ? `${(d.value / peak) * 100}%` : "2px" }}
						/>
					</div>
				))}
				{shown && hovered !== null ? (
					<div
						className="pointer-events-none absolute -top-2 -translate-x-1/2 rounded-full bg-ink px-2.5 py-0.5 text-[12px] whitespace-nowrap text-panel-solid"
						style={{ left: `${Math.min(92, Math.max(8, ((hovered + 0.5) / days.length) * 100))}%` }}
					>
						{shown.day}: {shown.value}
					</div>
				) : null}
			</div>
			<figcaption className="mt-1.5 flex justify-between font-heading text-[12px] text-ink-muted">
				<span>{days[0]?.day}</span>
				<span>{days[days.length - 1]?.day}</span>
			</figcaption>
			{dated.length > 0 ? (
				<details className="mt-2 text-[14px]">
					<summary className="link flex h-10 w-fit cursor-pointer items-center">
						See every day
					</summary>
					<div className="-mx-6 mt-1 max-h-72 overflow-y-auto">
						<Table
							head={[day("Day"), figure(unit)]}
							rows={dated.map((d) => [d.day, show(d.value)])}
							empty={null}
						/>
					</div>
				</details>
			) : null}
		</figure>
	);
}

export function Loading() {
	return <p className="px-6 pb-5 text-[14px]">Loading…</p>;
}

/**
 * A failure, and what to do about it. `bare` is for one inside a panel that
 * is already on the page.
 */
export function Failed({
	error,
	onRetry,
	bare = false,
}: {
	error: unknown;
	onRetry?: () => void;
	bare?: boolean;
}) {
	const body = (
		<div role="alert" className="flex flex-wrap items-center justify-between gap-4 px-6 py-5">
			<div className="min-w-0 flex-1">
				<p className="text-[15px] font-bold">That didn't work.</p>
				<p className="text-[14px] text-ink-muted">{plainMessage(error)}</p>
			</div>
			{onRetry ? (
				<button type="button" onClick={onRetry} className={buttonClass("secondary")}>
					Try again
				</button>
			) : null}
		</div>
	);
	return bare ? body : <Panel>{body}</Panel>;
}
