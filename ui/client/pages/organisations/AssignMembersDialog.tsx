/**
 * AssignMembersDialog — put members on one of the organisation's projects,
 * any number in one go. Assigning is additive and takes effect on save,
 * never on a stray click; taking someone off stays on the chip row behind
 * its confirm, because it stops their tracking.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import type { OrgProject } from "@/entities/organisation";
import { useAssignMembers, useMembers } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import { LIST } from "./styles";

export interface AssignMembersDialogProps {
	organisationId: string;
	project: OrgProject;
	onClose: () => void;
}

export function AssignMembersDialog({
	organisationId,
	project,
	onClose,
}: AssignMembersDialogProps) {
	const id = useId();
	const members = useMembers(organisationId);
	const assign = useAssignMembers(organisationId);
	const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
	const [error, setError] = useState<string | null>(null);

	const onIt = new Set(project.members.filter((a) => !a.endedAt).map((a) => a.userId));
	// `/members` answers the active ones already.
	const free = (members.data ?? []).filter((m) => !onIt.has(m.userId));
	const chosen = free.filter((m) => picked.has(m.userId));

	const toggle = (userId: string) => {
		setPicked((prev) => {
			const next = new Set(prev);
			if (next.has(userId)) next.delete(userId);
			else next.add(userId);
			return next;
		});
	};

	const save = async () => {
		if (chosen.length === 0) return;
		setError(null);
		try {
			await assign.mutateAsync({ projectId: project.id, userIds: chosen.map((m) => m.userId) });
			toast.success(
				chosen.length === 1
					? `${chosen[0].name} is on ${project.name}`
					: `${chosen.length} members are on ${project.name}`,
			);
			onClose();
		} catch (err) {
			// Whoever was assigned before the failure stays assigned; the list
			// refreshes under the dialog, so what is left to pick is accurate.
			setError(describeError(err, "The members could not be assigned."));
		}
	};

	return (
		<Dialog
			open
			onClose={() => !assign.isPending && onClose()}
			title={`Assign members to ${project.name}`}
			description="Anyone picked is on the project from the moment you assign them: their hours on it become the organisation's, nothing before."
			contentClassName="sm:w-full sm:max-w-[420px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void save();
				}}
				noValidate
				className="space-y-3"
			>
				{!members.data ? (
					<p className="text-[12.5px] text-muted-foreground py-2">Loading…</p>
				) : free.length === 0 ? (
					<p className="text-[12.5px] text-muted-foreground py-2">
						Every member of the organisation is already on this project.
					</p>
				) : (
					<ul className={`${LIST} max-h-72 overflow-y-auto`}>
						{free.map((m) => (
							<li key={m.userId}>
								<label
									htmlFor={`${id}-${m.userId}`}
									className="flex items-center gap-2.5 py-2 cursor-pointer"
								>
									<input
										id={`${id}-${m.userId}`}
										type="checkbox"
										checked={picked.has(m.userId)}
										onChange={() => toggle(m.userId)}
										className="accent-accent shrink-0"
									/>
									<span className="min-w-0">
										<span className="block text-[13px] font-bold text-foreground truncate">
											{m.name}
										</span>
										<span className="block text-xs text-muted-foreground truncate">{m.email}</span>
									</span>
								</label>
							</li>
						))}
					</ul>
				)}

				{error && (
					<p role="alert" className="text-sm text-destructive-ink">
						{error}
					</p>
				)}

				<div className="flex justify-end gap-2.5 pt-1">
					<Button
						type="button"
						variant="secondary"
						size="sm"
						onClick={onClose}
						disabled={assign.isPending}
					>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={assign.isPending || chosen.length === 0}>
						{assign.isPending
							? "Assigning…"
							: chosen.length > 1
								? `Assign ${chosen.length} members`
								: "Assign"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
