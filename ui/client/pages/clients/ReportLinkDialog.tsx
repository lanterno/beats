/**
 * ReportLinkDialog — "Share a report with Studio Kite" (docs/billing.md,
 * phase 1c): which finished days, which of the client's billed projects,
 * whether the link shows amounts and notes (both off: off is the narrow
 * side), the zone its days are counted in, how long it opens for, and a
 * label only the freelancer sees. Beside the form on a wide screen, under it
 * on a phone, the report exactly as the client will read it: the preview
 * route's answer, drawn by the report page's own view, with what to check
 * before sending in plain sentences above it.
 *
 * Its expiry is picked, never filled in: Create stays off until one of the
 * chips is chosen. The create is `createReportLink`, a plain `post` from
 * the click handler, sent once; the token it answers with lives in this
 * component's state and nowhere else, and is shown once, as the address a
 * client opens. Closing before Copy asks once. Replacing a link turns the
 * old one off first, so a failure leaves no old link working.
 *
 * `ReportLinkPreviewDialog` draws an existing link's report, read-only.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import {
	createReportLink,
	deleteReportLink,
	type ExpiryChoice,
	expiryFor,
	type RangeChoice,
	type ReportLink,
	type ReportScopeInput,
	rangeFor,
	reportUrl,
	todayIn,
	useReportPreview,
} from "@/entities/report-link";
import { ApiError, apiFieldErrors, describeError, reportLinksRootKey } from "@/shared/api";
import { addIsoDays, browserTimeZone, cn, formatDateShort, parseIsoDate } from "@/shared/lib";
import type { PublicReport } from "@/shared/report";
import { Button, Dialog, useConfirm } from "@/shared/ui";
import { ClientReportView } from "@/widgets/client-report";

export interface ReportLinkDialogProps {
	clientId: string;
	clientName: string;
	/** The client's billed projects, by name: what a link may cover. */
	billedProjects: readonly { id: string; name: string }[];
	/** The link this one replaces: the form starts from it, and it is turned off first. */
	replacing?: ReportLink;
	onClose: () => void;
}

type Range = { kind: "chip"; choice: RangeChoice } | { kind: "pick"; first: string; last: string };

interface Errors {
	days?: string;
	projects?: string;
	expiry?: string;
	general: string[];
}

const LABEL =
	"block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]";
const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-medium placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent aria-invalid:ring-2 aria-invalid:ring-destructive/60 disabled:opacity-60";
const ERROR = "mt-1 text-xs text-destructive-ink";
const HINT = "mt-1 text-xs text-muted-foreground font-medium";
const CHIP =
	"inline-flex items-center rounded-full px-2.5 py-0.5 text-[11.5px] font-bold transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
const CHECK = "w-4 h-4 shrink-0 accent-[hsl(var(--accent))]";
const SENTENCE = "text-[12.5px] font-medium text-foreground leading-normal";

const RANGE_CHIPS: [RangeChoice, string][] = [
	["last-month", "Last month"],
	["last-3-months", "Last 3 months"],
	["this-month", "This month to yesterday"],
];

const EXPIRY_CHIPS: [ExpiryChoice, string][] = [
	[30, "30 days"],
	[90, "90 days"],
	[365, "1 year"],
];

function chipClass(on: boolean): string {
	return cn(
		CHIP,
		on
			? "bg-accent text-accent-foreground"
			: "bg-secondary text-foreground hover:bg-sidebar-accent",
	);
}

/** "Nov 17, 2026". */
function longDay(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? `${formatDateShort(d)}, ${d.getFullYear()}` : iso;
}

/** "12.50 h", to the hundredth, as the report prints it. */
function hoursFixed(hours: number): string {
	return `${hours.toFixed(2)} h`;
}

/** Every zone the browser knows, the one in use among them. */
function timeZones(current: string): string[] {
	const supported =
		(Intl as unknown as { supportedValuesOf?: (key: "timeZone") => string[] }).supportedValuesOf?.(
			"timeZone",
		) ?? [];
	return supported.includes(current) ? supported : [current, ...supported];
}

/** `value` once it has stopped changing for `ms`: the preview is asked for once per pause. */
function useSettled<T>(value: T, ms: number): T {
	const key = JSON.stringify(value);
	const [settled, setSettled] = useState(value);
	useEffect(() => {
		const timer = setTimeout(() => setSettled(JSON.parse(key) as T), ms);
		return () => clearTimeout(timer);
	}, [key, ms]);
	return settled;
}

/**
 * What to check before sending, from the preview and the form: hours the
 * client will see with no amount, notes that will be shown, the billed
 * projects left out, and that the names are shown as written.
 */
function previewSentences(
	report: PublicReport,
	clientName: string,
	leftOut: readonly string[],
): string[] {
	const out: string[] = [];
	if (report.shows.amounts) {
		const unpriced = new Map<string, number>();
		for (const month of report.months) {
			for (const line of month.lines) {
				if ("rate_minor" in line && line.rate_minor === null) {
					unpriced.set(line.project_name, (unpriced.get(line.project_name) ?? 0) + line.hours);
				}
			}
		}
		for (const [name, hours] of unpriced) {
			out.push(
				`${hoursFixed(hours)} on ${name} have no rate yet; your client will see them without an amount.`,
			);
		}
	}
	if (report.shows.notes) {
		const notes = report.months.reduce(
			(sum, month) => sum + month.days.reduce((n, day) => n + (day.notes?.length ?? 0), 0),
			0,
		);
		if (notes > 0) {
			out.push(
				notes === 1
					? "1 note will be shown. Read it before you send."
					: `${notes} notes will be shown. Read them before you send.`,
			);
		}
	}
	if (leftOut.length > 0) out.push(`Not included: ${leftOut.join(", ")}.`);
	out.push(`${clientName} and the project names are shown as you wrote them.`);
	return out;
}

/** A refused create, onto the inputs: a 409's or 422's paths are the body's keys. */
function linkErrors(err: unknown, projectNames: readonly string[]): Errors {
	const out: Errors = { general: [] };
	const fields = apiFieldErrors(err);
	if (Object.keys(fields).length === 0) {
		out.general.push(describeError(err, "Failed to make the link"));
		return out;
	}
	for (const [path, message] of Object.entries(fields)) {
		const project = /^project_ids\.(\d+)$/.exec(path);
		if (project) {
			out.projects ??= `${projectNames[Number(project[1])] ?? "A project"}: ${message}`;
		} else if (path === "project_ids") out.projects ??= message;
		else if (path === "first" || path === "last") out.days ??= message;
		else if (path === "expires_on") out.expiry ??= message;
		else out.general.push(path ? `${path}: ${message}` : message);
	}
	return out;
}

/** The preview, or why there is none yet, with its sentences above it. */
function PreviewColumn({
	scope,
	tz,
	clientName,
	leftOut,
	invalid,
}: {
	scope: ReportScopeInput;
	tz: string;
	clientName: string;
	leftOut: readonly string[];
	/** Why the scope cannot be previewed yet, from the form's own checks. */
	invalid?: string;
}) {
	const settled = useSettled({ scope, tz, invalid }, 400);
	// Asked for only when the form and its settled copy are both valid: just
	// after a fix, the settled scope is still the one the form refused, and
	// the API would refuse it too.
	const preview = useReportPreview(settled.scope, settled.tz, {
		enabled: !invalid && !settled.invalid,
	});
	return (
		<section aria-label="Preview" className="min-w-0 rounded-[1.25rem] bg-secondary p-2.5 sm:p-3">
			<h3 className={cn(LABEL, "px-1.5")}>What your client will see</h3>
			{invalid ? (
				<p className={cn(SENTENCE, "px-1.5 text-muted-foreground")}>{invalid}</p>
			) : preview.error ? (
				<p className={cn(SENTENCE, "px-1.5 text-destructive-ink")} role="alert">
					{describeError(preview.error, "The preview could not be read.")}
				</p>
			) : !preview.data ? (
				<p className={cn(SENTENCE, "px-1.5 text-muted-foreground")}>Loading…</p>
			) : (
				<>
					<ul className="mb-2.5 px-1.5 space-y-1">
						{previewSentences(preview.data, clientName, leftOut).map((sentence) => (
							<li key={sentence} className={SENTENCE}>
								{sentence}
							</li>
						))}
					</ul>
					<div className={cn(preview.isFetching && "opacity-60 transition-opacity")}>
						<ClientReportView report={preview.data} today={new Date()} />
					</div>
				</>
			)}
		</section>
	);
}

/** The made link, shown once: its address, Copy, and what to know before sending it. */
function MadeLink({
	url,
	onCopied,
	onDone,
}: {
	url: string;
	onCopied: () => void;
	onDone: () => void;
}) {
	const id = useId();
	const field = useRef<HTMLInputElement>(null);
	const [hint, setHint] = useState<string | null>(null);

	const copy = async () => {
		onCopied();
		if (window.isSecureContext && navigator.clipboard) {
			try {
				await navigator.clipboard.writeText(url);
				setHint("Copied.");
				return;
			} catch {
				// Refused: select it for the keyboard, as without a clipboard.
			}
		}
		// A plain-http self-hosted address has no clipboard API.
		field.current?.focus();
		field.current?.select();
		const mac = /Mac|iPhone|iPad/.test(navigator.userAgent);
		setHint(`Press ${mac ? "⌘C" : "Ctrl+C"} to copy it.`);
	};

	return (
		<div className="space-y-3.5">
			<div>
				<label htmlFor={`${id}-url`} className={LABEL}>
					Report link
				</label>
				<div className="flex items-center gap-2">
					<input
						ref={field}
						id={`${id}-url`}
						type="text"
						readOnly
						value={url}
						onFocus={(e) => e.currentTarget.select()}
						aria-describedby={hint ? `${id}-hint` : undefined}
						className={cn(FIELD, "font-code text-[12.5px]")}
					/>
					<Button type="button" size="sm" onClick={() => void copy()}>
						Copy
					</Button>
				</div>
				{hint && (
					<p id={`${id}-hint`} className={HINT} aria-live="polite">
						{hint}
					</p>
				)}
			</div>
			<ul className="space-y-1.5">
				<li className={cn(SENTENCE, "font-bold")}>
					This is the only time this link is shown. If you lose it, turn it off and make another.
				</li>
				<li className={SENTENCE}>
					Email security tools may open the link on your client's behalf.
				</li>
				<li className={SENTENCE}>
					Sending to two people? Make one link each, so you can turn one off without the other.
				</li>
			</ul>
			<div className="flex justify-end pt-1">
				<Button type="button" variant="secondary" size="sm" onClick={onDone}>
					Done
				</Button>
			</div>
		</div>
	);
}

export function ReportLinkDialog({
	clientId,
	clientName,
	billedProjects,
	replacing,
	onClose,
}: ReportLinkDialogProps) {
	const id = useId();
	const queryClient = useQueryClient();
	const { confirm, confirmDialog } = useConfirm();
	const billedIds = new Set(billedProjects.map((project) => project.id));

	const [tz, setTz] = useState(replacing?.tz ?? browserTimeZone());
	const [zoneOpen, setZoneOpen] = useState(false);
	const [range, setRange] = useState<Range>(
		replacing
			? { kind: "pick", first: replacing.first, last: replacing.last }
			: { kind: "chip", choice: "last-month" },
	);
	const [selected, setSelected] = useState<ReadonlySet<string>>(() => {
		const kept = (replacing?.projects ?? [])
			.map((project) => project.id)
			.filter((id) => billedIds.has(id));
		return new Set(kept.length > 0 ? kept : billedIds);
	});
	const [showAmounts, setShowAmounts] = useState(replacing?.showAmounts ?? false);
	const [showNotes, setShowNotes] = useState(replacing?.showNotes ?? false);
	const [expiry, setExpiry] = useState<ExpiryChoice | null>(null);
	const [label, setLabel] = useState(replacing?.label ?? "");
	const [errors, setErrors] = useState<Errors>({ general: [] });
	const [busy, setBusy] = useState(false);
	// Once the replaced link is off, a failed create is retried as a new one.
	const [oldGone, setOldGone] = useState(false);
	// The token, once: only this state holds it, and it goes when the dialog does.
	const [token, setToken] = useState<string | null>(null);
	const [copied, setCopied] = useState(false);
	const [askedToClose, setAskedToClose] = useState(false);

	const today = todayIn(tz);
	const yesterday = addIsoDays(today, -1);
	const days =
		range.kind === "chip"
			? rangeFor(range.choice, today)
			: { first: range.first, last: range.last };
	const projectIds = billedProjects.map((p) => p.id).filter((id) => selected.has(id));
	const projectNames = projectIds.map(
		(id) => billedProjects.find((project) => project.id === id)?.name ?? "A project",
	);
	const leftOut = billedProjects.filter((p) => !selected.has(p.id)).map((p) => p.name);
	const scope: ReportScopeInput = {
		clientId,
		projectIds,
		first: days?.first ?? "",
		last: days?.last ?? "",
		showAmounts,
		showNotes,
	};
	const invalid =
		!days || !parseIsoDate(days.first) || !parseIsoDate(days.last)
			? "Pick the days the report covers."
			: days.last < days.first
				? "The last day comes before the first."
				: days.last >= today
					? "A report covers finished days; the last one can be yesterday."
					: projectIds.length === 0
						? "Pick at least one project."
						: undefined;

	const create = async () => {
		if (invalid || expiry === null || busy) return;
		setBusy(true);
		setErrors({ general: [] });
		let turnedOff = false;
		try {
			if (replacing && !oldGone) {
				try {
					await deleteReportLink(replacing.id);
				} catch (err) {
					// Already gone is as good as turned off.
					if (!(err instanceof ApiError && err.isNotFound())) {
						setErrors({ general: [describeError(err, "Failed to turn the old link off")] });
						return;
					}
				}
				turnedOff = true;
				setOldGone(true);
			}
			const made = await createReportLink(
				{ ...scope, label: label.trim() || undefined, expiresOn: expiryFor(expiry, today) },
				tz,
			);
			setToken(made.token);
		} catch (err) {
			const next = linkErrors(err, projectNames);
			if (turnedOff || oldGone) {
				next.general.unshift("The old link is off. Making the new one failed; try again.");
			}
			setErrors(next);
		} finally {
			setBusy(false);
			void queryClient.invalidateQueries({ queryKey: reportLinksRootKey });
		}
	};

	const close = async () => {
		if (busy) return;
		if (token && !copied && !askedToClose) {
			setAskedToClose(true);
			const sure = await confirm({
				title: "Close without copying the link?",
				detail:
					"This link won't be shown again. If you need it later, turn it off and make another.",
				confirmLabel: "Close",
				cancelLabel: "Keep it open",
			});
			if (!sure) return;
		}
		onClose();
	};

	const toggleProject = (projectId: string) =>
		setSelected((prev) => {
			const next = new Set(prev);
			if (next.has(projectId)) next.delete(projectId);
			else next.add(projectId);
			return next;
		});

	const fromId = `${id}-from`;
	const toId = `${id}-to`;
	const labelId = `${id}-label`;
	const zoneId = `${id}-zone`;

	return (
		<>
			<Dialog
				open
				onClose={() => void close()}
				title={`Share a report with ${clientName}`}
				description={
					token
						? "The link is made."
						: replacing && !oldGone
							? `Replaces ${replacing.label ?? "an untitled link"}: the old link is turned off first.`
							: "A link your client opens with no sign-in, to their billable hours."
				}
				contentClassName={
					token ? "sm:w-full sm:max-w-[520px]" : "sm:w-[calc(100vw-2rem)] sm:max-w-[1040px]"
				}
			>
				{token ? (
					<MadeLink
						url={reportUrl(window.location.origin, token)}
						onCopied={() => setCopied(true)}
						onDone={() => void close()}
					/>
				) : (
					<div className="grid gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)] lg:items-start">
						<form
							onSubmit={(e) => {
								e.preventDefault();
								void create();
							}}
							noValidate
							className="space-y-3.5 min-w-0"
						>
							<fieldset className="min-w-0 border-0 p-0 m-0">
								<legend className={LABEL}>Days</legend>
								<div className="flex flex-wrap gap-1.5">
									{RANGE_CHIPS.map(([choice, text]) => (
										<button
											key={choice}
											type="button"
											aria-pressed={range.kind === "chip" && range.choice === choice}
											disabled={rangeFor(choice, today) === null}
											onClick={() => setRange({ kind: "chip", choice })}
											className={chipClass(range.kind === "chip" && range.choice === choice)}
										>
											{text}
										</button>
									))}
									<button
										type="button"
										aria-pressed={range.kind === "pick"}
										onClick={() =>
											setRange({
												kind: "pick",
												first: days?.first ?? yesterday,
												last: days?.last ?? yesterday,
											})
										}
										className={chipClass(range.kind === "pick")}
									>
										Pick days…
									</button>
								</div>
								{range.kind === "pick" && (
									<div className="mt-2 grid grid-cols-2 gap-2">
										<div className="min-w-0">
											<label htmlFor={fromId} className={LABEL}>
												From
											</label>
											<input
												id={fromId}
												type="date"
												value={range.first}
												max={yesterday}
												onChange={(e) => setRange({ ...range, first: e.target.value })}
												aria-invalid={errors.days ? true : undefined}
												className={cn(FIELD, "font-mono font-bold")}
											/>
										</div>
										<div className="min-w-0">
											<label htmlFor={toId} className={LABEL}>
												To
											</label>
											<input
												id={toId}
												type="date"
												value={range.last}
												max={yesterday}
												onChange={(e) => setRange({ ...range, last: e.target.value })}
												aria-invalid={errors.days ? true : undefined}
												className={cn(FIELD, "font-mono font-bold")}
											/>
										</div>
									</div>
								)}
								<p className={HINT}>
									Finished days only, up to yesterday. Days counted in{" "}
									<span className="font-bold text-foreground">{tz}</span> ·{" "}
									<button
										type="button"
										aria-expanded={zoneOpen}
										aria-controls={zoneId}
										onClick={() => setZoneOpen((open) => !open)}
										className={LINKISH}
									>
										Change
									</button>
								</p>
								{zoneOpen && (
									<select
										id={zoneId}
										aria-label="Time zone"
										value={tz}
										onChange={(e) => setTz(e.target.value)}
										className={cn(FIELD, "mt-1.5")}
									>
										{timeZones(tz).map((zone) => (
											<option key={zone} value={zone}>
												{zone}
											</option>
										))}
									</select>
								)}
								{errors.days && <p className={ERROR}>{errors.days}</p>}
							</fieldset>

							<fieldset className="min-w-0 border-0 p-0 m-0">
								<legend className={LABEL}>Projects</legend>
								<ul className="flex flex-col gap-1">
									{billedProjects.map((project) => (
										<li key={project.id}>
											<label className="flex items-center gap-2 text-[13px] font-medium text-foreground">
												<input
													type="checkbox"
													checked={selected.has(project.id)}
													onChange={() => toggleProject(project.id)}
													className={CHECK}
												/>
												<span className="min-w-0 break-words">{project.name}</span>
											</label>
										</li>
									))}
								</ul>
								{errors.projects && <p className={ERROR}>{errors.projects}</p>}
							</fieldset>

							<fieldset className="min-w-0 border-0 p-0 m-0 space-y-1.5">
								<legend className={LABEL}>Shows</legend>
								<label className="flex items-start gap-2 text-[13px] font-medium text-foreground">
									<input
										type="checkbox"
										checked={showAmounts}
										onChange={(e) => setShowAmounts(e.target.checked)}
										className={cn(CHECK, "mt-0.5")}
									/>
									<span>
										Show amounts
										<span className="block text-xs text-muted-foreground">
											Rates and amounts, as on your invoice. Off: hours only.
										</span>
									</span>
								</label>
								<label className="flex items-start gap-2 text-[13px] font-medium text-foreground">
									<input
										type="checkbox"
										checked={showNotes}
										onChange={(e) => setShowNotes(e.target.checked)}
										className={cn(CHECK, "mt-0.5")}
									/>
									<span>
										Include notes
										<span className="block text-xs text-muted-foreground">
											Each day's session notes, as you wrote them.
										</span>
									</span>
								</label>
							</fieldset>

							<fieldset className="min-w-0 border-0 p-0 m-0">
								<legend className={LABEL}>Works until</legend>
								<div className="flex flex-wrap gap-1.5">
									{EXPIRY_CHIPS.map(([choice, text]) => (
										<button
											key={choice}
											type="button"
											aria-pressed={expiry === choice}
											onClick={() => setExpiry(choice)}
											className={chipClass(expiry === choice)}
										>
											{text}
										</button>
									))}
								</div>
								<p className={HINT}>
									{expiry === null
										? "Pick how long it opens for. It can be turned off sooner."
										: `Opens through ${longDay(expiryFor(expiry, today))}, then stops.`}
								</p>
								{errors.expiry && <p className={ERROR}>{errors.expiry}</p>}
							</fieldset>

							<div>
								<label htmlFor={labelId} className={LABEL}>
									Label
								</label>
								<input
									id={labelId}
									type="text"
									value={label}
									maxLength={120}
									onChange={(e) => setLabel(e.target.value)}
									placeholder="October invoice"
									aria-describedby={`${labelId}-hint`}
									className={FIELD}
								/>
								<p id={`${labelId}-hint`} className={HINT}>
									Only you see this.
								</p>
							</div>

							{errors.general.length > 0 && (
								<div className="text-sm text-destructive-ink space-y-0.5" role="alert">
									{errors.general.map((message) => (
										<p key={message}>{message}</p>
									))}
								</div>
							)}

							<div className="flex items-center flex-wrap justify-end gap-2.5 pt-1">
								<Button
									type="button"
									variant="secondary"
									size="sm"
									onClick={() => void close()}
									disabled={busy}
								>
									Cancel
								</Button>
								<Button
									type="submit"
									size="sm"
									disabled={busy || expiry === null || invalid !== undefined}
								>
									{busy ? "Creating…" : "Create"}
								</Button>
							</div>
						</form>

						<PreviewColumn
							scope={scope}
							tz={tz}
							clientName={clientName}
							leftOut={leftOut}
							invalid={invalid}
						/>
					</div>
				)}
			</Dialog>
			{confirmDialog}
		</>
	);
}

/** An existing link's report, as its client reads it today: nothing to change here. */
export function ReportLinkPreviewDialog({
	link,
	clientName,
	onClose,
}: {
	link: ReportLink;
	clientName: string;
	onClose: () => void;
}) {
	const scope: ReportScopeInput = {
		clientId: link.clientId,
		projectIds: link.projects.map((project) => project.id),
		first: link.first,
		last: link.last,
		showAmounts: link.showAmounts,
		showNotes: link.showNotes,
	};
	return (
		<Dialog
			open
			onClose={onClose}
			title={link.label ?? "Untitled link"}
			description={`The report this link shows ${clientName}, as it stands today.`}
			contentClassName="sm:w-[calc(100vw-2rem)] sm:max-w-[760px]"
		>
			<PreviewColumn scope={scope} tz={link.tz} clientName={clientName} leftOut={[]} />
		</Dialog>
	);
}
