/**
 * ManagedContractDialog — the employer's view of one assignment's contract:
 * whether the organisation manages it, and, where it does, the terms.
 *
 * Terms are editable only while the organisation manages the contract. The
 * API would take a term write either way, but on an unmanaged assignment the
 * terms are the member's own, and writing them from here would be the silent
 * recomputation decision 21 exists to prevent: management starts from the
 * terms the member recorded, and the employer's changes arrive afterwards as
 * audited acts. So while unmanaged this dialog still toggles and nothing
 * more; taking the pen is a save of its own, and the terms open after it.
 *
 * Every term write PUTs the whole contract beside `managed`, as the member's
 * panel PUTs the whole contract: the API's `keep_unsent_contract_fields`
 * holds the holiday lists and the entitlement, which only the member's own
 * form edits. A write dated inside an approved month comes back 409
 * PERIOD_APPROVED, which is shown as it is given.
 */

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { useManagedContract, useSetManagedContract } from "@/entities/organisation";
import type { Contract, ContractTerm } from "@/entities/project";
import {
	ContractTermDialog,
	describeTerm,
	placeTerm,
	sortTerms,
	termFormDefaults,
	termOn,
	toApiContract,
	toContract,
} from "@/entities/project";
import type { ApiContract } from "@/shared/api";
import { describeError } from "@/shared/api";
import { formatDateOnly, todayIso } from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";
import { LABEL, LEAD } from "./styles";

type Editor = { mode: "add" } | { mode: "edit"; index: number };

export function ManagedContractDialog({
	organisationId,
	projectId,
	projectName,
	userId,
	memberName,
	onClose,
}: {
	organisationId: string;
	projectId: string;
	projectName: string;
	userId: string;
	memberName: string;
	onClose: () => void;
}) {
	const read = useManagedContract(organisationId, projectId, userId);
	const save = useSetManagedContract(organisationId);
	// Derived, not synced: the stored value with the user's unsent answer
	// over it. An effect copying the query in would overwrite the toggle on
	// any refetch an invalidation causes.
	const [override, setOverride] = useState<boolean | null>(null);
	const [editor, setEditor] = useState<Editor | null>(null);
	const changeButton = useRef<HTMLButtonElement | null>(null);

	const data = read.data;
	const managed = override ?? data?.managed ?? false;
	const dirty = data !== undefined && managed !== data.managed;
	const contract: Contract | null = data?.contract ? toContract(data.contract) : null;
	const terms = contract ? sortTerms(contract.terms) : [];
	const today = todayIso();
	const current = contract ? termOn(contract, today) : undefined;
	// Both answers must say managed: the stored one, because terms are the
	// employer's to write only once the pen has actually changed hands, and
	// the one on screen, because an unsaved "hand it back" is an intent to
	// stop writing them.
	const editable = contract !== null && (data?.managed ?? false) && managed;

	const saveNow = () => {
		if (!data) return;
		save.mutate(
			{ projectId, userId, contract: data.contract, managed },
			{
				onSuccess: () => {
					toast.success(
						managed ? "The organisation manages the contract" : "Management handed back",
					);
					onClose();
				},
				onError: (err) => toast.error(describeError(err, "The contract could not be saved.")),
			},
		);
	};

	/** Write the whole contract with `terms` replaced — already in the API's
	 * order (`placeTerm`, or a filter over the sorted list) — keeping
	 * management on. */
	const saveTerms = (next: ContractTerm[], done: () => void, onError?: (err: unknown) => void) => {
		if (!contract) return;
		const nextContract: ApiContract = toApiContract({ ...contract, terms: next });
		save.mutate(
			{ projectId, userId, contract: nextContract, managed: true },
			{
				onSuccess: done,
				onError: (err) => {
					if (onError) onError(err);
					else toast.error(describeError(err, "The term could not be saved."));
				},
			},
		);
	};

	const removeTerm = (index: number) => {
		saveTerms(
			terms.filter((_, i) => i !== index),
			() => toast.success("Term removed"),
		);
	};

	return (
		<Dialog
			open
			onClose={() => !save.isPending && onClose()}
			title={`${memberName}'s contract on ${projectName}`}
			description="The terms start from what the member recorded; nothing is rewritten silently."
			contentClassName="sm:w-full sm:max-w-[420px]"
		>
			{read.error ? (
				<p className={LEAD} role="alert">
					{describeError(read.error, "The contract could not be read.")}
				</p>
			) : !data ? (
				<p className={LEAD}>Loading…</p>
			) : (
				<div className="space-y-3">
					<p className="text-[13px] font-medium text-foreground">
						{contract
							? `A contract with ${terms.length} dated ${terms.length === 1 ? "term" : "terms"} is on record.`
							: "No contract is on record."}
					</p>
					<label className="flex items-center gap-2 text-[13px] font-medium text-foreground">
						<input
							type="checkbox"
							checked={managed}
							onChange={(e) => setOverride(e.target.checked)}
							className="accent-accent"
						/>
						Managed by the organisation
					</label>

					{editable && (
						<div className="space-y-1.5 rounded-2xl bg-secondary p-3">
							<h3 className={LABEL}>Terms</h3>
							<ul className="space-y-1">
								{terms.map((term, index) => (
									<li
										key={term.effectiveFrom}
										className="flex items-center gap-2 text-[13px] text-foreground"
									>
										<span className="flex-1 min-w-0">
											<span className="tabular-nums">{formatDateOnly(term.effectiveFrom)}</span>
											{" · "}
											{describeTerm(term)}
											{term.effectiveFrom === current?.effectiveFrom && (
												<span className="ml-1 text-[11px] text-muted-foreground">(in force)</span>
											)}
										</span>
										<button
											type="button"
											onClick={() => setEditor({ mode: "edit", index })}
											disabled={save.isPending}
											className="text-muted-foreground hover:text-foreground disabled:opacity-50"
											aria-label={`Edit the term from ${formatDateOnly(term.effectiveFrom)}`}
										>
											<Pencil className="w-3.5 h-3.5" aria-hidden="true" />
										</button>
										<button
											type="button"
											onClick={() => removeTerm(index)}
											// A contract needs a term: the last one cannot go.
											disabled={save.isPending || terms.length === 1}
											className="text-muted-foreground hover:text-destructive-ink disabled:opacity-50"
											aria-label={`Remove the term from ${formatDateOnly(term.effectiveFrom)}`}
										>
											<Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
										</button>
									</li>
								))}
							</ul>
							<button
								type="button"
								ref={changeButton}
								onClick={() => setEditor({ mode: "add" })}
								disabled={save.isPending}
								className="inline-flex items-center gap-1 text-[13px] font-medium text-accent-ink hover:underline disabled:opacity-50"
							>
								<Plus className="w-3.5 h-3.5" aria-hidden="true" />
								Change contract from…
							</button>
						</div>
					)}

					<p className={LEAD}>
						While managed, the contract is the organisation's hand: {memberName}'s own writes to its
						terms, absences and adjustments are refused, and their days off become requests a
						decider answers. Handing it back returns all of that to them.{" "}
						{editable
							? "A term dated inside an approved month is refused until the month is reopened."
							: managed && !(data.managed ?? false)
								? "Save to take the contract under management; its terms can then be edited here."
								: "Terms are the member's own while it is unmanaged, edited on their project page."}
					</p>

					<div className="flex justify-end gap-2.5 pt-1">
						<Button
							type="button"
							variant="secondary"
							size="sm"
							onClick={onClose}
							disabled={save.isPending}
						>
							{dirty ? "Cancel" : "Close"}
						</Button>
						<Button type="button" size="sm" onClick={saveNow} disabled={save.isPending || !dirty}>
							{save.isPending ? "Saving…" : "Save"}
						</Button>
					</div>
				</div>
			)}

			{editor && contract && (
				<ContractTermDialog
					key={editor.mode === "edit" ? `edit-${editor.index}` : "add"}
					title={editor.mode === "edit" ? "Edit term" : "Change contract from…"}
					initial={
						editor.mode === "edit"
							? termFormDefaults(terms[editor.index])
							: // A new term starts from the current numbers, dated today.
								termFormDefaults(current ?? terms[terms.length - 1], {
									effectiveFrom: today,
									note: "",
								})
					}
					takenDates={terms
						.filter((_, i) => !(editor.mode === "edit" && i === editor.index))
						.map((t) => t.effectiveFrom)}
					submitting={save.isPending}
					fieldPrefix="contract"
					returnFocus={() => changeButton.current}
					onClose={() => setEditor(null)}
					onSave={(term, onError) => {
						const placed = placeTerm(terms, editor.mode === "edit" ? editor.index : null, term);
						saveTerms(
							placed.terms,
							() => {
								toast.success(editor.mode === "edit" ? "Term updated" : "Contract changed");
								setEditor(null);
							},
							(err) => onError(err, placed.savedIndex),
						);
					}}
				/>
			)}
		</Dialog>
	);
}
