/**
 * Review before acting: what a command will change, who notices and whether
 * it can be taken back — read before anything is typed, and on a page of its
 * own so the dangerous act is never the easiest thing on a list of accounts
 * (docs/backoffice.md § The line, § Commands).
 *
 * What will change comes from `POST /commands/{name}/preview`, which passes
 * the runner's own gates and writes nothing, so a mistyped id or a window
 * already queued is answered here rather than after an address is typed. The
 * "after" column, who notices and whether it can be undone are fixed text
 * per command (shared/commands.ts): the API cannot answer them without
 * running the thing.
 */

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { OperatorApiError } from "@/shared/api/client";
import { previewCommand, runCommand } from "@/shared/api/commands";
import {
	type CommandField,
	type CommandSpec,
	commandSpec,
	emptyArgs,
	FAMILIES,
	familyOf,
	fieldsOf,
	ON_THE_RECORD,
} from "@/shared/commands";
import { plainMessage } from "@/shared/lib/errors";
import { useSettled } from "@/shared/lib/useSettled";
import {
	buttonClass,
	Chip,
	Empty,
	Facts,
	Failed,
	Id,
	Loading,
	Page,
	Panel,
	Prose,
	Table,
	TextField,
} from "@/shared/ui";

/**
 * A 422 from the preview means the arguments do not parse yet — a reason not
 * written, a limit left as text. It is the form talking, not a failure, so
 * the page asks for the rest instead of showing an error.
 */
export function isIncomplete(error: unknown): boolean {
	return error instanceof OperatorApiError && error.statusCode === 422;
}

/** A day and minute, as the operator reads an instant. */
const minute = (iso: string | null | undefined): string =>
	typeof iso === "string" && iso ? iso.slice(0, 16).replace("T", " ") : "—";

function Fields({
	fields,
	args,
	onChange,
}: {
	fields: CommandField[];
	args: Record<string, unknown>;
	onChange: (key: string, value: unknown) => void;
}) {
	return (
		<div className="flex flex-wrap items-start gap-4 px-6 pb-5">
			{fields.map((field) =>
				field.kind === "checkbox" ? (
					<label key={field.key} className="flex max-w-[22rem] items-start gap-2 text-[14px]">
						<input
							type="checkbox"
							checked={Boolean(args[field.key])}
							onChange={(e) => onChange(field.key, e.target.checked)}
							className="mt-0.5 size-4 accent-[var(--leaf)]"
						/>
						<span>
							{field.label}
							{field.hint ? (
								<span className="block text-[13px] text-ink-muted">{field.hint}</span>
							) : null}
						</span>
					</label>
				) : (
					<div
						key={field.key}
						className={field.kind === "number" ? "w-36" : "min-w-[16rem] flex-1"}
					>
						<TextField
							label={field.label}
							value={String(args[field.key] ?? "")}
							inputMode={field.kind === "number" ? "numeric" : undefined}
							onChange={(e) => onChange(field.key, e.target.value)}
						/>
						{field.hint ? <p className="mt-1 text-[13px] text-ink-muted">{field.hint}</p> : null}
					</div>
				),
			)}
		</div>
	);
}

/** The acts available on this subject, so one can be swapped for another
 * without going back. */
function Pick({ spec, subject, chosen }: { spec: CommandSpec; subject: string; chosen: string }) {
	return (
		// biome-ignore lint/a11y/useSemanticElements: a fieldset cannot be a rounded flex track across browsers
		<div
			role="group"
			aria-label="What do you want to do?"
			className="flex flex-wrap gap-1 px-6 pb-4"
		>
			{familyOf(spec).map((other) => (
				<Link
					key={other.name}
					to={`/review/${other.name}/${subject}`}
					aria-current={other.name === chosen ? "true" : undefined}
					className={`inline-flex h-9 items-center rounded-full px-3.5 text-[14px] ${
						other.name === chosen ? "bg-wash-strong font-bold" : "hover:bg-wash"
					}`}
				>
					{other.title}
				</Link>
			))}
		</div>
	);
}

export function Review() {
	const { command = "", subject = "" } = useParams();
	// One review per command and subject. Moving to another (a Pick link)
	// keeps this route mounted, and without the key its typed fields and its
	// finished act would carry over to a command that has not run.
	return <CommandReview key={`${command}/${subject}`} />;
}

function CommandReview() {
	const { command = "", subject = "" } = useParams();
	const spec = commandSpec(command);
	const queryClient = useQueryClient();
	// A page may hand a field's value in the URL (the Trust page hands the
	// network key to slow); only declared fields are read, nothing else.
	const [search] = useSearchParams();
	const [args, setArgs] = useState<Record<string, unknown>>(() => {
		if (!spec) return {};
		const empty = emptyArgs(spec, subject);
		for (const field of fieldsOf(spec, subject)) {
			const given = search.get(field.key);
			if (given !== null && field.kind !== "checkbox") empty[field.key] = given;
		}
		return empty;
	});
	const family = FAMILIES[spec?.family ?? "account"];
	const fields = spec ? fieldsOf(spec, subject) : [];
	const [typed, setTyped] = useState("");

	// Previewed with the arguments as they stand, once typing has stopped:
	// the route validates them exactly as the act will, so an unfilled field
	// comes back 422 and that is the page's own "there is more to fill in",
	// not a failure. Settled, or every keystroke would be a request.
	const sentArgs = sent(fields, args);
	const settledArgs = useSettled(sentArgs);
	// A subjectless command makes its subject; the route's is a placeholder.
	const named = spec?.subjectless ? {} : { [family.subjectKey]: subject };
	const preview = useQuery({
		queryKey: ["preview", command, subject, settledArgs],
		queryFn: () => previewCommand(command, { ...named, ...settledArgs }),
		enabled: Boolean(spec && subject),
		retry: false,
		// The subject's "Now" stays on screen while the next preview loads.
		placeholderData: keepPreviousData,
	});

	const act = useMutation({
		mutationFn: () => runCommand(command, { ...named, ...sentArgs }, typed || undefined),
		onSuccess: () => {
			// Not the preview: once the act has run, "Now" is the state it
			// found, and re-reading it would make the change table claim the
			// account was always in the state the act just put it in.
			for (const key of [
				"account",
				"account-audit",
				"operator-jobs",
				"attention",
				"controls",
				"operator-queue",
				"erasure-requests",
			]) {
				queryClient.invalidateQueries({ queryKey: [key] });
			}
		},
	});

	// Only the first preview blanks the page. A later one loads under the
	// form, or the field being typed in would unmount, and lose focus, each
	// time typing stops; `previewed` below keeps the act shut meanwhile.
	const answered = useRef(false);
	if (!preview.isPending) answered.current = true;

	if (!spec) {
		return (
			<Page title="No such command" back={{ to: "/accounts", label: "Back to accounts" }}>
				<Panel>
					<Empty title="This page reviews a command.">
						Open an account, or access and controls, and choose one of its acts.
					</Empty>
				</Panel>
			</Page>
		);
	}

	const back = family.back(subject);

	if (preview.isPending && !answered.current) return <Loading />;
	const incomplete = isIncomplete(preview.error);
	if (preview.error && !incomplete) {
		return (
			<Page title={spec.title} back={back} lead="Nothing has happened.">
				<Failed error={preview.error} onRetry={() => preview.refetch()} />
			</Page>
		);
	}

	const before = (preview.data?.before ?? {}) as Record<string, unknown>;
	// `describe()` answers {exists: false} for an account that is not there.
	// A command that asks for the email never gets this far — looking the
	// address up is what 404s — but one that asks for nothing would, and the
	// change table would read the absence as a live, active account.
	const missing = before.exists === false;
	const done = act.data;
	// A windowed command answers {queued, job}; an inline one answers its
	// audit row. Both mean it worked, and they are read differently.
	const queued = Boolean(done && "queued" in done);
	const blocked = preview.data?.already_queued === true;
	const needsTyping = preview.data?.confirmation_required === true;
	// The act runs only what was reviewed: typing has settled, and the
	// preview has answered for these arguments — not still loading, and not
	// the previous one kept on screen meanwhile.
	const previewed =
		!preview.isPending &&
		!preview.isPlaceholderData &&
		JSON.stringify(sentArgs) === JSON.stringify(settledArgs);
	const ready =
		previewed && !blocked && !done && !incomplete && (!needsTyping || typed.trim().length > 0);

	return (
		<Page
			title={done ? "Done. Here is what changed." : "Check what will change, then do it."}
			back={back}
			lead={
				done ? (
					"It is on the record, and its page already shows it."
				) : spec.subjectless ? (
					"Nothing has happened yet."
				) : (
					<>
						Acting on <Id>{subject}</Id>. Nothing has happened yet.
					</>
				)
			}
		>
			<div className="grid gap-[18px] lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
				<div className="flex min-w-0 flex-col gap-[18px]">
					<Panel title="What do you want to do?">
						<Pick spec={spec} subject={subject} chosen={command} />
						<Prose>{spec.about}</Prose>
						{fields.length > 0 && !done ? (
							<Fields
								fields={fields}
								args={args}
								onChange={(key, value) => setArgs({ ...args, [key]: value })}
							/>
						) : null}
					</Panel>

					<Panel raised danger={spec.grave} title={done ? "What happened" : "Do it"}>
						{done ? (
							<>
								<Facts
									items={[
										["Command", spec.title],
										...(spec.subjectless
											? []
											: ([["Subject", <Id key="s">{subject}</Id>]] as Array<[string, ReactNode]>)),
										[
											"Where it is",
											queued
												? `Queued, runs from ${minute(preview.data?.runs_after)} UTC`
												: "Done, and on the record",
										],
									]}
								/>
								<div className="flex flex-wrap gap-2 px-6 pt-1 pb-5">
									<Link to={back.to} className={buttonClass("primary")}>
										{back.label}
									</Link>
									<Link to="/audit" className={buttonClass("secondary")}>
										See it in the audit
									</Link>
								</div>
							</>
						) : missing ? (
							<div className="px-6 pb-5">
								<p className="text-[15px] font-bold">{family.missing}</p>
								<p className="mt-1 text-[14px] text-ink-muted">
									Nothing here will act on it. Check it against where it came from.
								</p>
								<Link to={back.to} className={`${buttonClass("secondary")} mt-3`}>
									{back.label}
								</Link>
							</div>
						) : blocked ? (
							<div className="px-6 pb-5">
								<p className="text-[15px] font-bold">This is already queued for this account.</p>
								<p className="mt-1 text-[14px] text-ink-muted">
									One window at a time, by design. Cancel the one waiting before queueing another.
								</p>
								<Link to="/jobs" className={`${buttonClass("secondary")} mt-3`}>
									Open jobs and windows
								</Link>
							</div>
						) : (
							<div className="px-6 pb-5">
								{needsTyping ? (
									<div className="mb-3 max-w-[26rem]">
										<TextField
											label={family.typedLabel}
											value={typed}
											onChange={(e) => setTyped(e.target.value)}
											autoComplete="off"
											spellCheck={false}
										/>
										<p className="mt-1 text-[13px] text-ink-muted">
											Typed from what you already know about the subject, never offered here.
										</p>
									</div>
								) : null}
								<div className="flex flex-wrap items-center gap-3">
									<button
										type="button"
										disabled={!ready || act.isPending}
										onClick={() => act.mutate()}
										className={buttonClass(spec.grave ? "danger" : "primary")}
									>
										{act.isPending ? "Working…" : spec.action}
									</button>
									<Link to={back.to} className={buttonClass("secondary")}>
										Leave it as it is
									</Link>
									{incomplete ? (
										<span className="text-[14px] text-ink-muted">
											Fill in the fields above first.
										</span>
									) : needsTyping && !typed.trim() ? (
										<span className="text-[14px] text-ink-muted">Type it to confirm.</span>
									) : null}
								</div>
								{act.error ? (
									<p role="alert" className="mt-3 text-[14px] text-persimmon-ink">
										{plainMessage(act.error)}
									</p>
								) : null}
							</div>
						)}
					</Panel>
				</div>

				<Panel raised title={done ? "What it changed" : "What will change"}>
					{missing ? (
						<Empty title="Nothing to show.">The subject does not resolve.</Empty>
					) : (
						<>
							<Table
								head={["What", "Now", "After"]}
								rows={spec.changes(before, args, subject).map((row) => [
									row.what,
									<span key="now" className="text-ink-muted">
										{row.now}
									</span>,
									<span key="after" className="font-bold">
										{row.after}
									</span>,
								])}
								empty={<Empty title="Nothing to show." />}
							/>
							<Facts
								items={[
									[
										"When",
										preview.data?.runs_after
											? `Runs from ${minute(preview.data.runs_after)} UTC`
											: "At once",
									],
									...(preview.data?.window_days
										? ([["You can stop it for", `${preview.data.window_days} days`]] as Array<
												[string, string]
											>)
										: []),
									["Who notices", spec.notices],
									["Can you undo it", spec.undo],
									["On the record", ON_THE_RECORD],
								]}
							/>
							{spec.grave ? (
								<div className="px-6 pb-5">
									<Chip tone="owed">This one is hard to take back</Chip>
								</div>
							) : null}
						</>
					)}
				</Panel>
			</div>
		</Page>
	);
}

/** Only the fields this command declares, with empty boxes left out so the
 * API reads them as their defaults: "the platform's default" for a limit
 * rather than zero, the fixed all-clear for a status message, no parts for
 * `affected`. A null would be refused wherever the default is not None.
 * A number box holding something that is not a number goes as typed, for
 * the API to refuse; read as NaN it would go as null, and a slow-down of
 * "1,000" would arrive as a pause. */
function sent(fields: CommandField[], args: Record<string, unknown>): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	for (const field of fields) {
		const value = args[field.key];
		if (field.kind === "checkbox") out[field.key] = Boolean(value);
		else if (value === undefined || value === null || String(value).trim() === "") continue;
		else if (field.key === "affected" && typeof value === "string")
			// The status commands take a list; the box is one line of names.
			out[field.key] = value
				.split(",")
				.map((v) => v.trim())
				.filter(Boolean);
		else if (field.kind === "number" && Number.isFinite(Number(value)))
			out[field.key] = Number(value);
		else out[field.key] = value;
	}
	return out;
}

export { sent };
