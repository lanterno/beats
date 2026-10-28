/**
 * Organisations — `/organisations`: the invitations waiting for this
 * account (who, as what — the way in is the link the inviter sent), the
 * organisations it is in, and the ones it left, each of which keeps a
 * read-only archive of the person's own hours (docs/organisations.md). A
 * new organisation is made here, and the account that makes it is its
 * first owner.
 *
 * A row per organisation whose only link was the organisation itself cost
 * three clicks to reach anything real — index, organisation, tab. Each is a
 * card instead, linking straight to the tabs this member's role can see
 * (`?tab=`, which the detail page round-trips) and to what the organisation
 * can see of them; the tabs come from `tabsFor`, the detail page's own
 * list, so a card never offers what the page would not show.
 */

import { Building2, Eye, Mail, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import type { Membership, MembershipEnd, OrganisationInput } from "@/entities/organisation";
import {
	OrganisationMark,
	ROLE_LABELS,
	readsRecord,
	useCreateOrganisation,
	useInvitations,
	useMemberships,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Button, Chip, Dialog, Panel } from "@/shared/ui";
import { tabsFor } from "./Organisation";
import { OrganisationForm } from "./OrganisationForm";
import { Section } from "./Section";
import { LEAD, LIST, PAGE, PAGE_TITLE, PAGEBAR, ROW } from "./styles";

const WHY: Record<MembershipEnd, string> = {
	left: "you left",
	removed: "you were removed",
	erased: "the account was erased",
};

/** A card's destination: a pill that opens one of the organisation's tabs. */
const DESTINATION =
	"inline-flex items-center rounded-full bg-secondary px-3 py-1 font-heading text-[12.5px] font-bold text-foreground hover:bg-sidebar-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

function OrganisationCard({ membership }: { membership: Membership }) {
	const { organisation: org, role } = membership;
	const tabs = tabsFor(role);
	// Readers see the organisation's record; everyone else sees their own
	// half of it — the same two pages the detail page links to.
	const seen = readsRecord(role)
		? { to: `/organisations/${org.id}/record`, label: "What they see" }
		: { to: `/organisations/${org.id}/visible`, label: "What they see of you" };

	return (
		<Panel padding="p-0" className="flex flex-col">
			<div className="flex items-center gap-2 flex-wrap px-5 pt-4 pb-3 border-b border-border">
				<Link
					to={`/organisations/${org.id}?tab=${tabs[0].value}`}
					className="flex items-center gap-2 min-w-0 rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				>
					<OrganisationMark
						name={org.name}
						logoUrl={org.logoUrl}
						size="md"
						className="text-foreground"
					/>
				</Link>
				<Chip className="shrink-0">{ROLE_LABELS[role]}</Chip>
				<span className="ml-auto text-[12.5px] font-mono text-muted-foreground whitespace-nowrap">
					since {formatDate(membership.joinedAt)}
				</span>
			</div>
			<div className="flex flex-wrap gap-1.5 px-5 py-4">
				{tabs.map((tab) => (
					<Link
						key={tab.value}
						to={`/organisations/${org.id}?tab=${tab.value}`}
						className={DESTINATION}
					>
						{tab.label}
					</Link>
				))}
				<Link to={seen.to} className={DESTINATION}>
					<Eye className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
					{seen.label}
				</Link>
			</div>
		</Panel>
	);
}

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
		<div className={PAGE}>
			<Panel padding="px-5 py-3" className={PAGEBAR}>
				<Building2 className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
				<h1 className={PAGE_TITLE}>Organisations</h1>
				{pending.length > 0 && (
					<Chip tone="warn">
						{pending.length} invitation{pending.length === 1 ? "" : "s"}
					</Chip>
				)}
				<Button type="button" size="sm" className="ml-auto" onClick={() => setCreating(true)}>
					<Plus className="w-3.5 h-3.5" aria-hidden="true" />
					New organisation
				</Button>
			</Panel>

			{invitations.error != null && (
				<Section label="Invitations" icon={Mail} bodyClassName="px-5 py-1">
					<p className={`${LEAD} py-3`} role="alert">
						{describeError(invitations.error, "Your invitations could not be read.")} The rest of
						the page works as usual.
					</p>
				</Section>
			)}
			{pending.length > 0 && (
				<Section label="Invitations" icon={Mail} bodyClassName="px-5 py-1">
					<ul className={LIST}>
						{pending.map((invitation) => (
							// Keyed with the expiry: one organisation can invite twice.
							<li key={`${invitation.organisation.id}-${invitation.expiresAt}`} className={ROW}>
								<OrganisationMark
									name={invitation.organisation.name}
									logoUrl={invitation.organisation.logoUrl}
									className="text-foreground"
								/>
								<Chip tone="warn">{ROLE_LABELS[invitation.role]}</Chip>
								<span className="ml-auto font-mono text-muted-foreground whitespace-nowrap">
									until {formatDate(invitation.expiresAt)}
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
				</Section>
			)}

			<Section label="Your organisations" icon={Building2} bodyClassName="p-5">
				{memberships.error ? (
					<div role="alert">
						<p className="text-[13px] font-medium text-foreground">
							Organisations aren't available right now.
						</p>
						<p className="mt-1 text-xs text-muted-foreground">
							{describeError(memberships.error, "They could not be read.")}
						</p>
					</div>
				) : memberships.isLoading ? (
					<p className={LEAD}>Loading…</p>
				) : active.length === 0 ? (
					<div>
						<p className="font-heading text-lg font-extrabold text-foreground">
							An organisation owns projects and reads the hours on them.
						</p>
						<p className={`mt-1 ${LEAD}`}>
							Make one for your team, or accept an invitation. Your own projects stay yours either
							way.
						</p>
					</div>
				) : (
					<div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(340px,1fr))]">
						{active.map((m) => (
							<OrganisationCard key={m.organisation.id} membership={m} />
						))}
					</div>
				)}
			</Section>

			{left.length > 0 && (
				<Section label="Organisations you left" title="Left" bodyClassName="px-5 py-1">
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
									{m.leftReason && ` · ${WHY[m.leftReason]}`} · your hours are kept
								</span>
							</li>
						))}
					</ul>
				</Section>
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
