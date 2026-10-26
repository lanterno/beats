/**
 * TeamsSection — the organisation's teams, each a name and who is in it:
 * what gives a manager their scope, which is why each manager is marked on
 * their chip, a team with no manager says nobody decides for it, and a
 * manager in no team is named as seeing nothing. Deleting one takes
 * nothing else with it, which is what the confirmation says. Admins edit;
 * a manager reads it (`readOnly`) to see their own scope.
 */

import { Plus, UsersRound, X } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Team, TeamInput } from "@/entities/organisation";
import { useDeleteTeam, useMembers, useSaveTeam, useTeams } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, Dialog, useConfirm } from "@/shared/ui";
import { QueryBody, Section } from "./Section";
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
	// `/members` answers the active ones already.
	const active = members.data ?? [];

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

export function TeamsSection({
	organisationId,
	readOnly = false,
}: {
	organisationId: string;
	/** A manager reads their scope here; only admins change it. */
	readOnly?: boolean;
}) {
	const teams = useTeams(organisationId);
	const members = useMembers(organisationId);
	const deleteTeam = useDeleteTeam(organisationId);
	const { confirm, confirmDialog } = useConfirm();
	const [editor, setEditor] = useState<Editor | null>(null);

	const names = new Map((members.data ?? []).map((m) => [m.userId, m.name]));
	const managerIds = new Set(
		(members.data ?? []).filter((m) => m.role === "manager").map((m) => m.userId),
	);
	// A manager in no team has an empty scope: they decide for nobody and
	// their record shows nothing. Worth a line, since nothing else says it.
	const teamless = [...managerIds].filter(
		(uid) => !(teams.data ?? []).some((t) => t.memberIds.includes(uid)),
	);

	const remove = async (team: Team) => {
		const ok = await confirm({
			title: `Delete ${team.name}?`,
			detail: "The team's managers lose that scope; nothing else changes.",
			confirmLabel: "Delete",
			tone: "danger",
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
				readOnly ? undefined : (
					<button type="button" onClick={() => setEditor({ mode: "new" })} className={LINKISH}>
						<Plus className="w-3 h-3 inline-block mr-1" aria-hidden="true" />
						New team
					</button>
				)
			}
		>
			<QueryBody
				query={teams}
				errorText="The teams could not be read."
				empty="A team gives a manager their scope: they decide absences and timesheets for its members."
			>
				{(rows) => (
					<ul className={LIST}>
						{rows.map((team) => (
							<li key={team.id} className="py-3 space-y-2">
								<div className="flex items-center gap-2 text-[12.5px]">
									<span className="font-bold text-foreground truncate">{team.name}</span>
									{!readOnly && (
										<>
											<Button
												type="button"
												variant="secondary"
												size="sm"
												className="ml-auto h-7 px-2.5 text-xs"
												onClick={() => setEditor({ mode: "edit", team })}
												aria-label={`Edit ${team.name}`}
											>
												Edit
											</Button>
											<button
												type="button"
												onClick={() => void remove(team)}
												disabled={deleteTeam.isPending && deleteTeam.variables === team.id}
												aria-label={`Delete ${team.name}`}
												className={REMOVE}
											>
												<X className="w-3.5 h-3.5" aria-hidden="true" />
											</button>
										</>
									)}
								</div>
								<div className="flex flex-wrap items-center gap-1.5">
									{team.memberIds.length === 0 ? (
										<span className={LEAD}>Nobody on it yet.</span>
									) : (
										team.memberIds.map((userId) => (
											<span key={userId} className={CHIP}>
												{names.get(userId) ?? "Member"}
												{managerIds.has(userId) && (
													<span className="font-medium text-muted-foreground">Manager</span>
												)}
											</span>
										))
									)}
									{members.data && !team.memberIds.some((uid) => managerIds.has(uid)) && (
										<span className={LEAD}>
											No manager is in it — nobody decides for this team.
										</span>
									)}
								</div>
							</li>
						))}
					</ul>
				)}
			</QueryBody>
			{members.data && teams.data && teamless.length > 0 && (
				<p className={`${LEAD} py-2`}>
					{teamless.map((uid) => names.get(uid) ?? "A manager").join(", ")}{" "}
					{teamless.length === 1 ? "manages" : "manage"} no team yet, so their scope is empty.
				</p>
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
