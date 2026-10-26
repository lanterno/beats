/**
 * ManagedContractDialog — the employer's view of one assignment's contract:
 * whether the organisation manages it, toggled here and nothing more. The
 * terms themselves start from what the member recorded; editing them is the
 * member's project page while unmanaged, and the API while managed.
 */

import { useState } from "react";
import { toast } from "sonner";
import { useManagedContract, useSetManagedContract } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import { LEAD } from "./styles";

/** How many dated terms the wire contract carries, if it says. */
function termCount(contract: unknown): number | undefined {
	if (contract && typeof contract === "object" && "terms" in contract) {
		const terms = (contract as { terms?: unknown }).terms;
		if (Array.isArray(terms)) return terms.length;
	}
	return undefined;
}

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

	const data = read.data;
	const managed = override ?? data?.managed ?? false;
	const dirty = data !== undefined && managed !== data.managed;
	const terms = data ? termCount(data.contract) : undefined;

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
						{data.contract
							? terms !== undefined
								? `A contract with ${terms} dated ${terms === 1 ? "term" : "terms"} is on record.`
								: "A contract is on record."
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
					<p className={LEAD}>
						While managed, the contract is the organisation's hand: {memberName}'s own writes to its
						terms, absences and adjustments are refused, and their days off become requests a
						decider answers. Handing it back returns all of that to them. Terms are edited on the
						member's project page while unmanaged; managed terms change through the API for now.
					</p>
					<div className="flex justify-end gap-2.5 pt-1">
						<Button
							type="button"
							variant="secondary"
							size="sm"
							onClick={onClose}
							disabled={save.isPending}
						>
							Cancel
						</Button>
						<Button type="button" size="sm" onClick={saveNow} disabled={save.isPending || !dirty}>
							{save.isPending ? "Saving…" : "Save"}
						</Button>
					</div>
				</div>
			)}
		</Dialog>
	);
}
