/**
 * Whether the Organisations nav item wears a dot: while an invitation
 * addressed to this account is waiting (docs/organisations.md, decision
 * 11). The API sends no email, so the nav is where an invitation is found;
 * a failed read lights nothing.
 */

import { useInvitations } from "@/entities/organisation";

export function useInvitationAttention(): number {
	const { data, isError } = useInvitations();
	return isError ? 0 : (data?.length ?? 0);
}
