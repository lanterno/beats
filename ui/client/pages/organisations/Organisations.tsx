/**
 * Organisations — `/organisations`: the invitations waiting for this
 * account (who, as what — the way in is the link the inviter sent), the
 * organisations it is in, and the ones it left, each of which keeps a
 * read-only archive of the person's own hours (docs/organisations.md). A
 * new organisation is made here, and the account that makes it is its
 * first owner.
 */

import { Building2, Mail, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import type { Membership, MembershipEnd, OrganisationInput } from "@/entities/organisation";
import {
	OrganisationMark,
	ROLE_LABELS,
	useCreateOrganisation,
	useInvitations,
	useMemberships,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Button, Dialog, Panel } from "@/shared/ui";
import { OrganisationForm } from "./OrganisationForm";
import { HEADING, HEADING_ICON, LEAD, LINKISH, LIST, ROW, TITLE } from "./styles";

const WHY: Record<MembershipEnd, string> = {
	left: "you left",
	removed: "you were removed",
	erased: "the account was erased",
};

export default function Organisations() {
	const navigate = useNavigate();
	const [creating, setCreating] = useState(false);
	const invitations = useInvitations();
	const memberships = useMemberships();
	const create = useCreateOrganisation();

	const active = (memberships.data ?? []).filter((m) => !m.leftAt);
	const left = (memberships.data ?? []).filter((m) => m.leftAt);
	const pending = invitations.data ?? [];

	const saveNew = async (input: OrganisationInput) => {
		const membership: Membership = await create.mutateAsync(input);
		toast.success(`${membership.organisation.name} created`);
		setCreating(false);
		navigate(`/organisations/${membership.organisation.id}`);
	};

	return (
		<div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-8 pb-24">
			<header className="flex items-center gap-3 flex-wrap">
				<Building2 className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
				<h1 className={TITLE}>Organisations</h1>
				<Button type="button" size="sm" className="ml-auto" onClick={() => setCreating(true)}>
					<Plus className="w-3.5 h-3.5" aria-hidden="true" />
					New organisation
				</Button>
			</header>

			{pending.length > 0 && (
				<section aria-label="Invitations">
					<h2 className={HEADING}>
						<Mail className={HEADING_ICON} />
						Invitations
					</h2>
					<Panel padding="px-5 py-1">
						<ul className={LIST}>
							{pending.map((invitation) => (
								<li key={invitation.organisation.id} className={ROW}>
									<OrganisationMark
										name={invitation.organisation.name}
										logoUrl={invitation.organisation.logoUrl}
										className="text-foreground"
									/>
									<span className="text-muted-foreground">
										as a {ROLE_LABELS[invitation.role].toLowerCase()} · until{" "}
										{formatDate(invitation.expiresAt)}
									</span>
								</li>
							))}
						</ul>
						{/* The way in is the link, not this list: an address is not
						    verified at sign-up, so the API hands out no token here. */}
						<p className={`${LEAD} py-3`}>
							Open the invite link you were sent to join. If you don't have it, ask the person who
							invited you.
						</p>
					</Panel>
				</section>
			)}

			<section aria-label="Your organisations">
				<h2 className={HEADING}>
					<Building2 className={HEADING_ICON} />
					Your organisations
				</h2>
				{memberships.error ? (
					<Panel role="alert" padding="px-5 py-4">
						<p className="text-[13px] font-medium text-foreground">
							Organisations aren't available right now.
						</p>
						<p className="mt-1 text-xs text-muted-foreground">
							{describeError(memberships.error, "They could not be read.")}
						</p>
					</Panel>
				) : memberships.isLoading ? (
					<p className="text-sm text-muted-foreground px-2">Loading…</p>
				) : active.length === 0 ? (
					<Panel padding="px-6 py-[22px]">
						<p className="font-heading text-lg font-extrabold text-foreground">
							An organisation owns projects and reads the hours on them.
						</p>
						<p className={`mt-1 ${LEAD}`}>
							Make one for your team, or accept an invitation. Your own projects stay yours either
							way.
						</p>
					</Panel>
				) : (
					<Panel padding="px-5 py-1">
						<ul className={LIST}>
							{active.map((m) => (
								<li key={m.organisation.id} className={ROW}>
									<Link
										to={`/organisations/${m.organisation.id}`}
										className="flex items-center gap-2 min-w-0 rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
									>
										<OrganisationMark
											name={m.organisation.name}
											logoUrl={m.organisation.logoUrl}
											size="md"
											className="text-foreground"
										/>
									</Link>
									<span className="text-muted-foreground">{ROLE_LABELS[m.role]}</span>
									<span className="ml-auto text-muted-foreground whitespace-nowrap">
										since {formatDate(m.joinedAt)}
									</span>
								</li>
							))}
						</ul>
					</Panel>
				)}
			</section>

			{left.length > 0 && (
				<section aria-label="Organisations you left">
					<h2 className={HEADING}>Left</h2>
					<Panel padding="px-5 py-1">
						<ul className={LIST}>
							{left.map((m) => (
								<li key={m.organisation.id} className={ROW}>
									<Link
										to={`/organisations/${m.organisation.id}/archive`}
										className="font-bold text-foreground hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
									>
										{m.organisation.name} (left)
									</Link>
									<span className="text-muted-foreground">
										{m.leftAt && formatDate(m.leftAt)}
										{m.leftReason && ` · ${WHY[m.leftReason]}`}
									</span>
									<Link
										to={`/organisations/${m.organisation.id}/archive`}
										className={`${LINKISH} ml-auto`}
									>
										Your hours
									</Link>
								</li>
							))}
						</ul>
					</Panel>
				</section>
			)}

			{creating && (
				<Dialog
					open
					onClose={() => setCreating(false)}
					title="New organisation"
					description="You will be its first owner. Its projects appear on a member's list once they are assigned."
					contentClassName="sm:w-full sm:max-w-[460px]"
				>
					<OrganisationForm
						onSave={saveNew}
						onCancel={() => setCreating(false)}
						submitLabel="Create"
					/>
				</Dialog>
			)}
		</div>
	);
}
