/**
 * ContractHistoryPanel — a day job's terms over time, and the one place
 * they are edited. Modelled on OverrideManagementPanel: a list with a
 * delete affordance per row, plus "Change contract from…", which appends
 * a term, and a pencil per term for fixing one (its date included — people
 * fix dates). The last remaining term cannot be deleted; a contract needs
 * one. Every change PUTs the whole contract, as goal-overrides are saved.
 *
 * Terms are edited here and not in the settings form so a percentage
 * change is never ambiguous between "fix the current term" and "a new
 * term from this date" — they are two buttons.
 */

import { Calendar, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { type Ref, useState } from "react";
import { toast } from "sonner";
import type {
	Contract,
	ContractTerm,
	Project,
	TermFieldErrors,
	TermFormValues,
} from "@/entities/project";
import {
	ContractTermFields,
	contractFieldErrors,
	describeTerm,
	sortTerms,
	termFormDefaults,
	termFromForm,
	termOn,
	toApiContract,
	useUpdateContract,
	validateTerm,
} from "@/entities/project";
import { apiFieldErrors, describeError } from "@/shared/api";
import { formatDateOnly, todayIso } from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";

interface ContractHistoryPanelProps {
	project: Project;
	/** Opens the settings drawer — where a day job without a contract gets one. */
	onOpenSettings: () => void;
	/** The "Change contract from…" button, so the settings form can hand focus here. */
	changeButtonRef?: Ref<HTMLButtonElement>;
}

type Editor = { mode: "add" } | { mode: "edit"; index: number };

export function ContractHistoryPanel({
	project,
	onOpenSettings,
	changeButtonRef,
}: ContractHistoryPanelProps) {
	const updateContract = useUpdateContract();
	const [editor, setEditor] = useState<Editor | null>(null);
	const [pendingIndex, setPendingIndex] = useState<number | null>(null);

	if (project.kind !== "day_job") return null;
	const contract = project.contract;

	if (!contract) {
		return (
			<section
				id="contract-history"
				aria-labelledby="contract-history-title"
				className="rounded-lg border border-border/60 bg-secondary/10 p-3"
			>
				<h3
					id="contract-history-title"
					className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground mb-1"
				>
					Contract
				</h3>
				<p className="text-[11px] text-muted-foreground/70 mb-2">
					No contract yet. Add one to see what each week owes and your running balance.
				</p>
				<Button type="button" variant="outline" size="sm" onClick={onOpenSettings}>
					Add contract
				</Button>
			</section>
		);
	}

	const terms = sortTerms(contract.terms);
	const today = todayIso();
	const current = termOn(contract, today);
	const anyPending = updateContract.isPending;

	const handleDelete = (index: number) => {
		if (terms.length <= 1) return;
		setPendingIndex(index);
		const next: Contract = { ...contract, terms: terms.filter((_, i) => i !== index) };
		updateContract.mutate(
			{ projectId: project.id, contract: toApiContract(next) },
			{
				onSuccess: () => toast.success("Term removed"),
				// A delete has no inputs to pin a 422 to; the message is the toast.
				onError: (err) => toast.error(describeError(err, "Failed to remove term")),
				onSettled: () => setPendingIndex(null),
			},
		);
	};

	const editing = editor?.mode === "edit" ? terms[editor.index] : undefined;
	const otherDates = terms.filter((t) => t !== editing).map((t) => t.effectiveFrom);

	return (
		<section
			id="contract-history"
			aria-labelledby="contract-history-title"
			className="rounded-lg border border-border/60 bg-secondary/10 p-3"
		>
			<header className="flex items-center gap-1.5 mb-2">
				<h3
					id="contract-history-title"
					className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground"
				>
					Contract history
				</h3>
				<span className="text-[10px] text-muted-foreground/60">({terms.length})</span>
				<Button
					ref={changeButtonRef}
					type="button"
					variant="outline"
					size="sm"
					onClick={() => setEditor({ mode: "add" })}
					disabled={anyPending}
					className="ml-auto h-7 text-xs"
				>
					<Plus className="w-3 h-3" aria-hidden="true" />
					Change contract from…
				</Button>
			</header>
			<ul className="space-y-1">
				{terms.map((term, index) => {
					const isCurrent = term === current;
					const isPending = pendingIndex === index;
					const when = formatDateOnly(term.effectiveFrom);
					return (
						<li
							key={term.effectiveFrom}
							className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-xs ${
								isCurrent ? "bg-accent/10 border border-accent/30" : "bg-background/40"
							}`}
						>
							<Calendar className="w-3 h-3 text-muted-foreground/60 shrink-0" aria-hidden="true" />
							<span className="text-muted-foreground tabular-nums shrink-0">From</span>
							<span className="text-foreground tabular-nums shrink-0">{when}</span>
							<span className="text-foreground/80 shrink-0">·</span>
							<span className="text-foreground truncate min-w-0">{describeTerm(term)}</span>
							{isCurrent && (
								<span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-accent/40 text-accent shrink-0">
									In force
								</span>
							)}
							{term.note && (
								<span className="text-muted-foreground/70 truncate flex-1 min-w-0">
									· {term.note}
								</span>
							)}
							<span className="ml-auto flex items-center gap-0.5 shrink-0">
								<button
									type="button"
									onClick={() => setEditor({ mode: "edit", index })}
									disabled={anyPending}
									aria-label={`Edit term from ${when}`}
									className="p-1 rounded text-muted-foreground/50 hover:text-foreground hover:bg-secondary/60 transition-colors disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
								>
									<Pencil className="w-3 h-3" />
								</button>
								<button
									type="button"
									onClick={() => handleDelete(index)}
									disabled={anyPending || terms.length <= 1}
									aria-label={`Remove term from ${when}`}
									title={terms.length <= 1 ? "A contract needs at least one term" : undefined}
									className="p-1 rounded text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
								>
									{isPending ? (
										<Loader2 className="w-3 h-3 animate-spin" />
									) : (
										<Trash2 className="w-3 h-3" />
									)}
								</button>
							</span>
						</li>
					);
				})}
			</ul>

			{editor && (
				<TermDialog
					key={editor.mode === "edit" ? `edit-${editor.index}` : "add"}
					title={editor.mode === "edit" ? "Edit term" : "Change contract from…"}
					initial={
						editor.mode === "edit"
							? termFormDefaults(editing)
							: // A new term starts from the current numbers, dated today.
								termFormDefaults(current ?? terms[terms.length - 1], {
									effectiveFrom: today,
									note: "",
								})
					}
					takenDates={otherDates}
					submitting={anyPending}
					onClose={() => setEditor(null)}
					onSave={(term, onError) => {
						const nextTerms =
							editor.mode === "edit"
								? terms.map((t, i) => (i === editor.index ? term : t))
								: [...terms, term];
						const savedIndex = sortTerms(nextTerms).indexOf(term);
						const next: Contract = { ...contract, terms: sortTerms(nextTerms) };
						updateContract.mutate(
							{ projectId: project.id, contract: toApiContract(next) },
							{
								onSuccess: () => {
									toast.success(editor.mode === "edit" ? "Term updated" : "Contract changed");
									setEditor(null);
								},
								onError: (err) => onError(err, savedIndex),
							},
						);
					}}
				/>
			)}
		</section>
	);
}

interface TermDialogProps {
	title: string;
	initial: TermFormValues;
	/** effective_from dates of the other terms — no two may start on one day. */
	takenDates: string[];
	submitting: boolean;
	onClose: () => void;
	/** Hands the term over; `onError` brings a failed save's 422 back to the inputs. */
	onSave: (term: ContractTerm, onError: (err: unknown, savedIndex: number) => void) => void;
}

function TermDialog({ title, initial, takenDates, submitting, onClose, onSave }: TermDialogProps) {
	const [values, setValues] = useState<TermFormValues>(initial);
	const [errors, setErrors] = useState<TermFieldErrors>({});
	const [general, setGeneral] = useState<string[]>([]);

	const handleSubmit = () => {
		const next = validateTerm(values);
		if (!next.effectiveFrom && takenDates.includes(values.effectiveFrom)) {
			next.effectiveFrom = "Another term already starts on this day";
		}
		setErrors(next);
		setGeneral([]);
		if (Object.keys(next).length > 0) return;
		onSave(termFromForm(values), (err, savedIndex) => {
			// PUT /contract's body is the contract itself, so paths start at "terms".
			const sorted = contractFieldErrors(apiFieldErrors(err), "", savedIndex);
			setErrors(sorted.term);
			const messages = [...sorted.general];
			if (messages.length === 0 && Object.keys(sorted.term).length === 0) {
				messages.push(describeError(err, "Failed to save contract"));
			}
			setGeneral(messages);
		});
	};

	return (
		<Dialog
			open
			onClose={onClose}
			title={title}
			description="Any weekday works: a change on a Wednesday charges Monday and Tuesday at the old rate."
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					handleSubmit();
				}}
				className="space-y-4"
				noValidate
			>
				<ContractTermFields
					values={values}
					onChange={setValues}
					errors={errors}
					dateLabel="From"
					withNote
					autoFocusField="effectiveFrom"
				/>
				{general.length > 0 && (
					<div className="text-sm text-destructive space-y-0.5" role="alert">
						{general.map((message) => (
							<p key={message}>{message}</p>
						))}
					</div>
				)}
				<div className="flex gap-2 pt-1">
					<Button type="submit" disabled={submitting} className="flex-1">
						{submitting ? "Saving…" : "Save term"}
					</Button>
					<Button type="button" variant="outline" onClick={onClose}>
						Cancel
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
