/**
 * ConnectProjectDialog — connect a project already tracked personally to an
 * organisation the member belongs to (docs/organisations-roadmap.md, stage
 * 2, rule 4). The member picks the organisation and the day from which the
 * hours and absences on the project are the organisation's record, or
 * starts fresh and shares nothing before now; the project becomes the
 * organisation's — its name, colour and kind theirs to change — while the
 * goal, the local repo paths and the contract stay the member's.
 *
 * The API refuses a project billed to a client (PROJECT_HAS_BILLING), one
 * already an organisation's (ORGANISATION_PROJECT) and a day after today
 * (SHARE_FROM_IN_FUTURE); each refusal is shown in its own words above the
 * buttons rather than guessed at here.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import { describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import { useConnectProject } from "../api";
import type { Membership } from "../model";

export interface ConnectProjectDialogProps {
	project: { id: string; name: string };
	/** The member's active memberships: the organisations on offer. */
	memberships: Membership[];
	/** Today, YYYY-MM-DD: the latest day history can be shared from. */
	todayIso: string;
	onConnected: () => void;
	onClose: () => void;
}

const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-medium placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent disabled:opacity-60";
const LABEL =
	"block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]";
const OPTION =
	"flex items-start gap-2 rounded-2xl px-3 py-2 cursor-pointer transition-colors has-checked:bg-sidebar-accent bg-secondary hover:bg-sidebar-accent/60";

type Share = "fresh" | "from";

export function ConnectProjectDialog({
	project,
	memberships,
	todayIso,
	onConnected,
	onClose,
}: ConnectProjectDialogProps) {
	const id = useId();
	const connect = useConnectProject();
	const [organisationId, setOrganisationId] = useState(
		memberships.length === 1 ? memberships[0].organisation.id : "",
	);
	const [share, setShare] = useState<Share>("fresh");
	const [shareFrom, setShareFrom] = useState(todayIso);
	const [error, setError] = useState<unknown>(null);

	// An answer belongs to the inputs it answered: changing any clears it.
	const choose =
		<T,>(set: (v: T) => void) =>
		(value: T) => {
			setError(null);
			set(value);
		};
	const pickShare = choose(setShare);
	const pickShareFrom = choose(setShareFrom);
	const pickOrganisation = choose(setOrganisationId);

	const chosen = memberships.find((m) => m.organisation.id === organisationId);
	const canSubmit = chosen !== undefined && (share === "fresh" || shareFrom !== "");

	const submit = () => {
		if (!chosen) return;
		setError(null);
		connect.mutate(
			{
				organisationId: chosen.organisation.id,
				projectId: project.id,
				shareFrom: share === "from" ? shareFrom : null,
			},
			{
				onSuccess: () => {
					toast.success(`Connected to ${chosen.organisation.name}`);
					onConnected();
				},
				onError: setError,
			},
		);
	};

	const close = () => {
		if (!connect.isPending) onClose();
	};

	return (
		<Dialog
			open
			onClose={close}
			title={`Connect ${project.name}`}
			description="Make this project part of an organisation's working-time record."
			contentClassName="sm:w-full sm:max-w-[460px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					submit();
				}}
				noValidate
				className="space-y-4"
			>
				<div>
					<label htmlFor={`${id}-organisation`} className={LABEL}>
						Organisation
					</label>
					<select
						id={`${id}-organisation`}
						value={organisationId}
						onChange={(e) => pickOrganisation(e.target.value)}
						className={FIELD}
						autoFocus
					>
						{memberships.length !== 1 && <option value="">Choose an organisation…</option>}
						{memberships.map((m) => (
							<option key={m.organisation.id} value={m.organisation.id}>
								{m.organisation.name}
							</option>
						))}
					</select>
				</div>

				<fieldset>
					<legend className={LABEL}>Share history</legend>
					<div className="space-y-1.5">
						<label className={OPTION}>
							<input
								type="radio"
								name={`${id}-share`}
								value="fresh"
								checked={share === "fresh"}
								onChange={() => pickShare("fresh")}
								className="mt-1 shrink-0"
							/>
							<span className="text-sm font-medium text-foreground">
								Start fresh — share nothing before now
							</span>
						</label>
						<label className={OPTION}>
							<input
								type="radio"
								name={`${id}-share`}
								value="from"
								checked={share === "from"}
								onChange={() => pickShare("from")}
								className="mt-1 shrink-0"
							/>
							<span className="flex-1 min-w-0 space-y-1.5">
								<span className="block text-sm font-medium text-foreground">Share from a date</span>
								<input
									type="date"
									aria-label="Share from"
									value={shareFrom}
									max={todayIso}
									disabled={share !== "from"}
									onChange={(e) => pickShareFrom(e.target.value)}
									className={`${FIELD} w-auto font-mono font-bold bg-card`}
								/>
							</span>
						</label>
					</div>
					<p className="mt-2 text-xs text-muted-foreground leading-normal">
						{chosen?.organisation.name ?? "The organisation"} will see the hours and absences on
						this project from that day on, and nothing before.
					</p>
				</fieldset>

				<p className="text-xs text-muted-foreground leading-normal">
					The project becomes {chosen?.organisation.name ?? "the organisation"}'s: its name, colour
					and kind become theirs to change. Your goal, local repo paths and contract stay yours —
					though a contract that began before the day you share from keeps its balance to you, since
					a balance would carry what you kept back. There is no disconnect: the way out is leaving
					the organisation, which keeps the hours already shared as its record.
				</p>

				{error !== null && (
					<p className="text-sm text-destructive-ink" role="alert">
						{describeError(error, "Could not connect the project")}
					</p>
				)}

				<div className="flex justify-end gap-2.5 pt-1">
					<Button
						type="button"
						variant="secondary"
						size="sm"
						onClick={close}
						disabled={connect.isPending}
					>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={!canSubmit || connect.isPending}>
						{connect.isPending ? "Connecting…" : "Connect"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
