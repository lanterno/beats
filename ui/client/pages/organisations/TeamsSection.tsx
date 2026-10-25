/**
 * TeamsSection — the organisation's teams, each a name and who is in it:
 * what gives a manager their scope. Deleting one takes nothing else with
 * it, which is what the confirmation says. Admins only.
 */

import { Plus, UsersRound, X } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Team, TeamInput } from "@/entities/organisation";
import { useDeleteTeam, useMembers, useSaveTeam, useTeams } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, Dialog, useConfirm } from "@/shared/ui";
import { Section } from "./Section";
import { CHIP, ERROR, FIELD, LABEL, LEAD, LINKISH, LIST, REMOVE } from "./styles";

function TeamDialog({
	organisationId,
	team,
	onClose,
}: {
	organisationId: string;
	team?: Team;
	onClose: () => void;
}) {
	const id = useId();
	const members = useMembers(organisationId);
	const save = useSaveTeam(organisationId);
	const [name, setName] = useState(team?.name ?? "");
	const [memberIds, setMemberIds] = useState<Set<string>>(new Set(team?.memberIds ?? []));
	const [error, setError] = useState("");
	const active = (members.data ?? []).filter((m) => !m.leftAt);

	const toggle = (userId: string) =>
		setMemberIds((ids) => {
			const next = new Set(ids);
			if (next.has(userId)) next.delete(userId);
			else next.add(userId);
			return next;
		});

	const submit = async () => {
		if (!name.trim()) {
			setError("A team needs a name.");
			return;
		}
		setError("");
		const input: TeamInput = { name: name.trim(), memberIds: [...memberIds] };
		try {
			await save.mutateAsync({ teamId: team?.id, input });
			toast.success(team ? "Team saved" : "Team added");
			onClose();
		} catch (err) {
			setError(describeError(err, "The team could not be saved."));
		}
	};

	return (
		<Dialog
			open
			onClose={() => !save.isPending && onClose()}
			title={team ? "Edit team" : "New team"}
			description="A team gives a manager their scope: they decide absences and timesheets for its members."
			contentClassName="sm:w-full sm:max-w-[420px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void submit();
				}}
				noValidate
				className="space-y-3"
			>
				<div>
					<label htmlFor={`${id}-name`} className={LABEL}>
						Name
					</label>
					<input
						id={`${id}-name`}
						type="text"
						value={name}
						onChange={(e) => setName(e.target.value)}
						maxLength={120}
						autoFocus
						aria-invalid={error ? true : undefined}
						className={FIELD}
					/>
				</div>
				<fieldset className="border-0 p-0 m-0">
					<legend className={LABEL}>Members</legend>
					{active.length === 0 ? (
						<p className={LEAD}>No active members to put on it.</p>
					) : (
						<div className="max-h-56 overflow-y-auto space-y-1.5">
							{active.map((m) => (
								<label
									key={m.userId}
									className="flex items-center gap-2 text-[13px] font-medium text-foreground"
								>
									<input
										type="checkbox"
										checked={memberIds.has(m.userId)}
										onChange={() => toggle(m.userId)}
										className="accent-accent"
									/>
									{m.name}
								</label>
							))}
						</div>
					)}
				</fieldset>
				{error && (
					<p role="alert" className={ERROR}>
						{error}
					</p>
				)}
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
					<Button type="submit" size="sm" disabled={save.isPending}>
						{save.isPending ? "Saving…" : team ? "Save" : "Add team"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}

type Editor = { mode: "new" } | { mode: "edit"; team: Team };

export function TeamsSection({ organisationId }: { organisationId: string }) {
	const teams = useTeams(organisationId);
	const members = useMembers(organisationId);
	const deleteTeam = useDeleteTeam(organisationId);
	const { confirm, confirmDialog } = useConfirm();
	const [editor, setEditor] = useState<Editor | null>(null);

	const names = new Map((members.data ?? []).map((m) => [m.userId, m.name]));

	const remove = async (team: Team) => {
		const ok = await confirm({
			title: `Delete ${team.name}?`,
			detail: "The team's managers lose that scope; nothing else changes.",
			confirmLabel: "Delete",
		});
		if (!ok) return;
		deleteTeam.mutate(team.id, {
			onSuccess: () => toast.success(`${team.name} deleted`),
			onError: (err) => toast.error(describeError(err, "The team could not be deleted.")),
		});
	};

	return (
		<Section
			label="Teams"
			icon={UsersRound}
			action={
				<button type="button" onClick={() => setEditor({ mode: "new" })} className={LINKISH}>
					<Plus className="w-3 h-3 inline-block mr-1" aria-hidden="true" />
					New team
				</button>
			}
		>
			{teams.error ? (
				<p className={`${LEAD} py-3`} role="alert">
					{describeError(teams.error, "The teams could not be read.")}
				</p>
			) : !teams.data ? (
				<p className={`${LEAD} py-3`}>Loading…</p>
			) : teams.data.length === 0 ? (
				<p className={`${LEAD} py-3`}>
					A team gives a manager their scope: they decide absences and timesheets for its members.
				</p>
			) : (
				<ul className={LIST}>
					{teams.data.map((team) => (
						<li key={team.id} className="py-3 space-y-2">
							<div className="flex items-center gap-2 text-[12.5px]">
								<span className="font-bold text-foreground truncate">{team.name}</span>
								<Button
									type="button"
									variant="secondary"
									size="sm"
									className="ml-auto h-7 px-2.5 text-xs"
									onClick={() => setEditor({ mode: "edit", team })}
								>
									Edit
								</Button>
								<button
									type="button"
									onClick={() => void remove(team)}
									disabled={deleteTeam.isPending}
									aria-label={`Delete ${team.name}`}
									className={REMOVE}
								>
									<X className="w-3.5 h-3.5" aria-hidden="true" />
								</button>
							</div>
							<div className="flex flex-wrap items-center gap-1.5">
								{team.memberIds.length === 0 ? (
									<span className={LEAD}>Nobody on it yet.</span>
								) : (
									team.memberIds.map((userId) => (
										<span key={userId} className={CHIP}>
											{names.get(userId) ?? "Member"}
										</span>
									))
								)}
							</div>
						</li>
					))}
				</ul>
			)}
			{editor && (
				<TeamDialog
					key={editor.mode === "edit" ? editor.team.id : "new"}
					organisationId={organisationId}
					team={editor.mode === "edit" ? editor.team : undefined}
					onClose={() => setEditor(null)}
				/>
			)}
			{confirmDialog}
		</Section>
	);
}
