/**
 * ProjectsSection — the organisation's projects with who is on each.
 * Assigning — any number of members at once, through `AssignMembersDialog` —
 * puts the project on each member's list and makes their hours on it the
 * organisation's from now; a member who connected a project of their own
 * shows the date they chose (`describeShareFrom`). Taking a member off
 * stops their tracking to it and keeps the hours already shared, which is
 * why it asks first.
 */

import { Layers, Pencil, Plus, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import type { OrgProject, OrgRole } from "@/entities/organisation";
import {
	decides,
	describeShareFrom,
	useMembers,
	useOrgProjects,
	useUnassignMember,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, useConfirm } from "@/shared/ui";
import { AssignMembersDialog } from "./AssignMembersDialog";
import { EnterTimeDialog } from "./EnterTimeDialog";
import { KIND_LABELS } from "./kinds";
import { ManagedContractDialog } from "./ManagedContractDialog";
import { OrgProjectDialog } from "./OrgProjectDialog";
import { Section } from "./Section";
import { CHIP, LEAD, LINKISH, LIST } from "./styles";

type Editor = { mode: "new" } | { mode: "edit"; project: OrgProject };

/** One assignment a decider acts on: whose contract, or whose time. */
type MemberAct = {
	kind: "contract" | "time";
	projectId: string;
	projectName: string;
	userId: string;
	memberName: string;
};

export function ProjectsSection({
	organisationId,
	role,
}: {
	organisationId: string;
	role: OrgRole;
}) {
	const projects = useOrgProjects(organisationId);
	const members = useMembers(organisationId);
	const unassign = useUnassignMember(organisationId);
	const { confirm, confirmDialog } = useConfirm();
	const [editor, setEditor] = useState<Editor | null>(null);
	const [act, setAct] = useState<MemberAct | null>(null);
	const [assigning, setAssigning] = useState<string | null>(null);
	const mayDecide = decides(role);
	const active = (members.data ?? []).filter((m) => !m.leftAt);
	// The open dialog reads the project off the query, so an assignment that
	// lands while it is open narrows its list rather than going stale.
	const assigningProject = (projects.data ?? []).find((p) => p.id === assigning);

	const takeOff = async (project: OrgProject, userId: string, name: string) => {
		const ok = await confirm({
			title: `Take ${name} off ${project.name}?`,
			detail: `${project.name} leaves their list and their tracking to it stops. The hours already shared stay the organisation's.`,
			confirmLabel: "Take off",
		});
		if (!ok) return;
		unassign.mutate(
			{ projectId: project.id, userId },
			{
				onSuccess: () => toast.success(`${name} is off ${project.name}`),
				onError: (err) => toast.error(describeError(err, "The member could not be taken off.")),
			},
		);
	};

	return (
		<Section
			label="Projects"
			icon={Layers}
			action={
				<button type="button" onClick={() => setEditor({ mode: "new" })} className={LINKISH}>
					<Plus className="w-3 h-3 inline-block mr-1" aria-hidden="true" />
					New project
				</button>
			}
		>
			{projects.error ? (
				<p className={`${LEAD} py-3`} role="alert">
					{describeError(projects.error, "The projects could not be read.")}
				</p>
			) : !projects.data ? (
				<p className={`${LEAD} py-3`}>Loading…</p>
			) : projects.data.length === 0 ? (
				<p className={`${LEAD} py-3`}>
					No projects yet. A member tracks on one once they are assigned to it.
				</p>
			) : (
				<ul className={LIST}>
					{projects.data.map((project) => {
						const onIt = project.members.filter((a) => !a.endedAt);
						const assigned = new Set(onIt.map((a) => a.userId));
						const free = active.filter((m) => !assigned.has(m.userId));
						return (
							<li key={project.id} className="py-3 space-y-2">
								<div className="flex items-center gap-2 text-[12.5px]">
									<span
										className="w-2.5 h-2.5 rounded-full shrink-0"
										style={{ backgroundColor: project.color ?? "var(--color-muted-foreground)" }}
										aria-hidden="true"
									/>
									<span className="font-bold text-foreground truncate">{project.name}</span>
									<span className="text-muted-foreground">{KIND_LABELS[project.kind]}</span>
									{project.archived && <span className="text-muted-foreground">· archived</span>}
									<Button
										type="button"
										variant="secondary"
										size="sm"
										className="ml-auto h-7 px-2.5 text-xs"
										onClick={() => setEditor({ mode: "edit", project })}
									>
										<Pencil className="w-3 h-3" aria-hidden="true" />
										Edit
									</Button>
								</div>
								<div className="flex flex-wrap items-center gap-1.5">
									{onIt.map((a) => (
										<span key={a.userId} className={CHIP}>
											{a.name ?? "Member"}
											<span className="font-medium text-muted-foreground">
												{describeShareFrom(a.sharedFrom)}
											</span>
											<button
												type="button"
												onClick={() => void takeOff(project, a.userId, a.name ?? "this member")}
												disabled={unassign.isPending}
												aria-label={`Take ${a.name ?? "this member"} off ${project.name}`}
												className="grid place-items-center w-4 h-4 rounded-full text-muted-foreground hover:text-destructive-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
											>
												<X className="w-3 h-3" aria-hidden="true" />
											</button>
											{mayDecide && (
												<>
													<button
														type="button"
														onClick={() =>
															setAct({
																kind: "contract",
																projectId: project.id,
																projectName: project.name,
																userId: a.userId,
																memberName: a.name ?? "this member",
															})
														}
														aria-label={`Contract of ${a.name ?? "this member"} on ${project.name}`}
														className={LINKISH}
													>
														Contract…
													</button>
													<button
														type="button"
														onClick={() =>
															setAct({
																kind: "time",
																projectId: project.id,
																projectName: project.name,
																userId: a.userId,
																memberName: a.name ?? "this member",
															})
														}
														aria-label={`Enter time for ${a.name ?? "this member"} on ${project.name}`}
														className={LINKISH}
													>
														Enter time…
													</button>
												</>
											)}
										</span>
									))}
									{free.length > 0 ? (
										<button
											type="button"
											onClick={() => setAssigning(project.id)}
											aria-label={`Assign members to ${project.name}`}
											className={LINKISH}
										>
											<Plus className="w-3 h-3 inline-block mr-1" aria-hidden="true" />
											Assign members…
										</button>
									) : members.data && active.length <= 1 ? (
										<span className="text-xs text-muted-foreground">
											You're the only member —{" "}
											<Link to="?tab=people" className={LINKISH}>
												invite people
											</Link>{" "}
											to put them on it.
										</span>
									) : members.data ? (
										<span className="text-xs text-muted-foreground">
											Every member is on this project.
										</span>
									) : null}
								</div>
							</li>
						);
					})}
				</ul>
			)}
			{assigningProject && (
				<AssignMembersDialog
					key={assigningProject.id}
					organisationId={organisationId}
					project={assigningProject}
					onClose={() => setAssigning(null)}
				/>
			)}
			{editor && (
				<OrgProjectDialog
					key={editor.mode === "edit" ? editor.project.id : "new"}
					organisationId={organisationId}
					project={editor.mode === "edit" ? editor.project : undefined}
					onClose={() => setEditor(null)}
				/>
			)}
			{act?.kind === "contract" && (
				<ManagedContractDialog
					key={`${act.projectId}-${act.userId}`}
					organisationId={organisationId}
					projectId={act.projectId}
					projectName={act.projectName}
					userId={act.userId}
					memberName={act.memberName}
					onClose={() => setAct(null)}
				/>
			)}
			{act?.kind === "time" && (
				<EnterTimeDialog
					key={`${act.projectId}-${act.userId}`}
					organisationId={organisationId}
					projectId={act.projectId}
					projectName={act.projectName}
					userId={act.userId}
					memberName={act.memberName}
					onClose={() => setAct(null)}
				/>
			)}
			{confirmDialog}
		</Section>
	);
}
