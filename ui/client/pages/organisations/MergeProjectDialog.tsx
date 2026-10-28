/**
 * MergeProjectDialog — fold one of the organisation's projects into another
 * (docs/organisations.md decision 28): the way out of the duplicate a
 * connect leaves when the organisation already had a project for the same
 * work. Every row moves with its stamp untouched, so what each member chose
 * to share stays shared from that instant and nothing private crosses; the
 * merged project is deleted. A frozen month on either side refuses the
 * merge in the API's words (409 PERIOD_APPROVED) — shown, not retried.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import type { OrgProject } from "@/entities/organisation";
import { useMergeOrgProject } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import { FIELD, LABEL, LEAD } from "./styles";

export function MergeProjectDialog({
	organisationId,
	project,
	targets,
	onClose,
}: {
	organisationId: string;
	project: OrgProject;
	/** The organisation's other projects, offered as the surviving one. */
	targets: OrgProject[];
	onClose: () => void;
}) {
	const id = useId();
	const merge = useMergeOrgProject(organisationId);
	const [into, setInto] = useState<string>(targets[0]?.id ?? "");
	const [error, setError] = useState<string | null>(null);
	const target = targets.find((t) => t.id === into);

	const saveNow = () => {
		if (!target) return;
		setError(null);
		merge.mutate(
			{ projectId: project.id, into: target.id },
			{
				onSuccess: () => {
					toast.success(`${project.name} merged into ${target.name}`);
					onClose();
				},
				onError: (err) => setError(describeError(err, "The projects could not be merged.")),
			},
		);
	};

	return (
		<Dialog
			open
			onClose={() => !merge.isPending && onClose()}
			title={`Merge ${project.name} into…`}
			description="For a duplicate a connected project left: its history folds into the project that stays."
			contentClassName="sm:w-full sm:max-w-[420px]"
		>
			<div className="space-y-3">
				<div>
					<label htmlFor={`${id}-into`} className={LABEL}>
						The project that stays
					</label>
					<select
						id={`${id}-into`}
						value={into}
						onChange={(e) => setInto(e.target.value)}
						className={FIELD}
					>
						{targets.map((t) => (
							<option key={t.id} value={t.id}>
								{t.name}
							</option>
						))}
					</select>
				</div>
				<p className={LEAD}>
					Every member's hours move with what they chose to share unchanged, assignments fold into{" "}
					{target?.name ?? "the surviving project"}, and {project.name} is deleted. A month already
					approved on either project refuses the merge until it is reopened.
				</p>
				{error && (
					<p className="text-sm text-destructive-ink" role="alert">
						{error}
					</p>
				)}
				<div className="flex justify-end gap-2.5 pt-1">
					<Button
						type="button"
						variant="secondary"
						size="sm"
						onClick={onClose}
						disabled={merge.isPending}
					>
						Cancel
					</Button>
					<Button type="button" size="sm" onClick={saveNow} disabled={merge.isPending || !target}>
						{merge.isPending ? "Merging…" : "Merge"}
					</Button>
				</div>
			</div>
		</Dialog>
	);
}
