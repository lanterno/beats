/**
 * MembersSection — the active members, by the name and address each
 * joined under, with a role to change and a way to remove. The caller's
 * own row has no controls: a role is given by someone else, and the way
 * out of one's own membership is Leave. The API keeps the rules — the
 * owner role moves only by an owner's hand (403), the last owner keeps it
 * (409) — and its detail is what a refusal shows.
 */

import { Users, X } from "lucide-react";
import { toast } from "sonner";
import type { Member, OrgRole } from "@/entities/organisation";
import {
	ROLE_HINTS,
	ROLE_LABELS,
	useMembers,
	useRemoveMember,
	useSetMemberRole,
} from "@/entities/organisation";
import { useAuth } from "@/features/auth";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Chip, useConfirm } from "@/shared/ui";
import { Section } from "./Section";
import { LEAD, LIST, REMOVE, ROW, SELECT } from "./styles";

const ROLES: OrgRole[] = ["member", "viewer", "manager", "admin", "owner"];

export function MembersSection({ organisationId }: { organisationId: string }) {
	const { user } = useAuth();
	const members = useMembers(organisationId);
	const setRole = useSetMemberRole(organisationId);
	const remove = useRemoveMember(organisationId);
	const { confirm, confirmDialog } = useConfirm();

	const changeRole = (member: Member, role: OrgRole) =>
		setRole.mutate(
			{ userId: member.userId, role },
			{
				onSuccess: () => toast.success(`${member.name} is now ${ROLE_LABELS[role].toLowerCase()}`),
				onError: (err) => toast.error(describeError(err, "The role could not be changed.")),
			},
		);

	const removeMember = async (member: Member) => {
		const ok = await confirm({
			title: `Remove ${member.name}?`,
			detail: `Their tracking to the organisation's projects stops and the projects leave their list. The organisation keeps its record of their hours so far, and they keep a read-only archive.`,
			confirmLabel: "Remove",
		});
		if (!ok) return;
		remove.mutate(member.userId, {
			onSuccess: () => toast.success(`${member.name} removed`),
			onError: (err) => toast.error(describeError(err, "The member could not be removed.")),
		});
	};

	return (
		<Section
			label="Members"
			icon={Users}
			lead="Admins run the organisation; a manager decides for their teams; a viewer reads the record."
		>
			{members.error ? (
				<p className={`${LEAD} py-3`} role="alert">
					{describeError(members.error, "The members could not be read.")}
				</p>
			) : !members.data ? (
				<p className={`${LEAD} py-3`}>Loading…</p>
			) : (
				<ul className={LIST}>
					{members.data.map((member) => {
						const me = user?.email !== undefined && member.email === user.email;
						return (
							<li key={member.userId} className={ROW}>
								<div className="min-w-0 flex-1">
									<p className="font-bold text-foreground truncate">
										{member.name}
										{me && <span className="font-medium text-muted-foreground"> (you)</span>}
									</p>
									<p className="text-muted-foreground truncate">
										{member.email} · since {formatDate(member.joinedAt)}
									</p>
								</div>
								{me ? (
									<Chip className="shrink-0">{ROLE_LABELS[member.role]}</Chip>
								) : (
									<>
										<select
											value={member.role}
											onChange={(e) => changeRole(member, e.target.value as OrgRole)}
											disabled={setRole.isPending}
											aria-label={`Role of ${member.name}`}
											className={SELECT}
										>
											{ROLES.map((role) => (
												<option key={role} value={role} title={ROLE_HINTS[role]}>
													{ROLE_LABELS[role]}
												</option>
											))}
										</select>
										<button
											type="button"
											onClick={() => void removeMember(member)}
											disabled={remove.isPending}
											aria-label={`Remove ${member.name}`}
											className={REMOVE}
										>
											<X className="w-3.5 h-3.5" aria-hidden="true" />
										</button>
									</>
								)}
							</li>
						);
					})}
				</ul>
			)}
			{confirmDialog}
		</Section>
	);
}
