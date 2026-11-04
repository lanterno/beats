/**
 * One command as a small form: its fields, the typed confirmation where the
 * command demands one, and the refusal in the API's own words. Plain on
 * purpose — the dangerous act must not be the easiest thing on the page,
 * and typing the subject's name back is the point.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { runCommand } from "@/shared/api/commands";

export function CommandForm({
	name,
	label,
	args,
	confirmHint,
	fields,
	invalidates,
}: {
	name: string;
	label: string;
	args: Record<string, unknown>;
	/** What must be typed back, described ("the account's email"). Omitted
	 * for commands that need none. */
	confirmHint?: string;
	fields?: ReactNode;
	invalidates: string[];
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

	return (
		<form
			className="flex flex-wrap items-center gap-2 p-3 border-t border-neutral-100 first:border-0"
			onSubmit={(e) => {
				e.preventDefault();
				run.mutate();
			}}
		>
			<span className="text-sm w-44">{label}</span>
			{fields}
			{confirmHint ? (
				<input
					value={confirmation}
					onChange={(e) => setConfirmation(e.target.value)}
					placeholder={confirmHint}
					className="border border-neutral-300 rounded px-2 py-1 text-sm w-64"
				/>
			) : null}
			<button
				type="submit"
				disabled={run.isPending}
				className="border border-neutral-300 rounded px-3 py-1 text-sm bg-neutral-50 disabled:opacity-50"
			>
				{run.isPending ? "…" : "Run"}
			</button>
			{run.error ? (
				<span className="text-sm text-red-700">
					{run.error instanceof Error ? run.error.message : "Refused"}
				</span>
			) : null}
			{run.isSuccess ? <span className="text-sm text-neutral-500">Done.</span> : null}
		</form>
	);
}
