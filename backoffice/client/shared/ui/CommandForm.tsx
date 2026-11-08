/**
 * One command as a row of a panel: what it is, its fields, the typed
 * confirmation where the command demands one, and the refusal in words the
 * operator can act on. Typing the subject's name back is the point: the
 * dangerous act must not be the easiest thing on the page, so its button
 * stays dim until something has been typed, and never wears the sun.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, type SyntheticEvent, useState } from "react";
import { runCommand } from "@/shared/api/commands";
import { plainMessage } from "@/shared/lib/errors";
import { buttonClass, TextField } from "@/shared/ui";

export function CommandForm({
	name,
	label,
	about,
	action,
	done = "Done.",
	args,
	confirmHint,
	fields,
	invalidates,
	inline = false,
}: {
	name: string;
	/** What this is. Inline, the button's accessible name. */
	label: string;
	/** What happens, where the label doesn't already say. */
	about?: ReactNode;
	/** The button: a verb and its object. */
	action: string;
	/** Said once it has worked. */
	done?: string;
	args: Record<string, unknown>;
	/** What must be typed back, as an instruction ("Type the account's email
	 * to confirm"). Omitted for commands that need none. */
	confirmHint?: string;
	fields?: ReactNode;
	invalidates: string[];
	/** Just the button, for a row of a table. */
	inline?: boolean;
}) {
	const [confirmation, setConfirmation] = useState("");
	const queryClient = useQueryClient();
	const run = useMutation({
		mutationFn: () => runCommand(name, args, confirmation || undefined),
		onSuccess: () => {
			setConfirmation("");
			for (const key of invalidates) {
				queryClient.invalidateQueries({ queryKey: [key] });
			}
		},
	});

	const submit = (e: SyntheticEvent) => {
		e.preventDefault();
		run.mutate();
	};
	const button = (
		<button
			type="submit"
			aria-label={inline ? label : undefined}
			disabled={run.isPending || (confirmHint !== undefined && confirmation === "")}
			className={buttonClass(confirmHint ? "danger" : "secondary")}
		>
			{run.isPending ? "Working…" : action}
		</button>
	);
	const outcome = run.error ? (
		<span role="alert" className="text-[13px] text-persimmon-ink">
			{plainMessage(run.error)}
		</span>
	) : run.isSuccess ? (
		<span role="status" className="text-[13px] text-leaf-ink">
			{done}
		</span>
	) : null;

	if (inline) {
		return (
			<form className="flex items-center justify-end gap-2.5" onSubmit={submit}>
				{outcome}
				{button}
			</form>
		);
	}

	return (
		<form
			className="grid gap-x-6 gap-y-3 border-t border-hairline px-6 py-4 md:grid-cols-[minmax(0,15rem)_1fr]"
			onSubmit={submit}
		>
			<div>
				<h3 className="text-[15px] font-bold">{label}</h3>
				{about ? <p className="text-[13px] leading-snug text-ink-muted">{about}</p> : null}
			</div>
			<div className="flex flex-wrap items-end justify-end gap-3">
				{fields}
				{confirmHint ? (
					<TextField
						label={confirmHint}
						value={confirmation}
						onChange={(e) => setConfirmation(e.target.value)}
						autoComplete="off"
						className="min-w-[15rem] flex-1"
					/>
				) : null}
				{button}
				{outcome ? <div className="basis-full text-right">{outcome}</div> : null}
			</div>
		</form>
	);
}
