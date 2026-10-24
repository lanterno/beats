/**
 * Organisation — `/organisations/:id`: one organisation and the caller's
 * standing in it (docs/organisations-roadmap.md, stage 2). For everyone:
 * what the organisation can see, in plain sentences with a link to the
 * data itself, and the way out. For admins and owners: the members, the
 * invites, the join requests, the projects with who is on each, and the
 * settings — each a section in the settings page's voice. The API resolves
 * the caller's membership first on every route here, so a 404 is "not a
 * member", and the archive is what remains of one that ended.
 */

import { Building2, Eye, LogOut, Settings } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import type { Membership, OrganisationInput } from "@/entities/organisation";
import {
	canAdminister,
	OrganisationMark,
	ROLE_LABELS,
	useLeaveOrganisation,
	useMembership,
	useUpdateOrganisation,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Panel, useConfirm } from "@/shared/ui";
import { InvitesSection } from "./InvitesSection";
import { JoinRequestsSection } from "./JoinRequestsSection";
import { MembersSection } from "./MembersSection";
import { OrganisationForm } from "./OrganisationForm";
import { ProjectsSection } from "./ProjectsSection";
import { HEADING, HEADING_ICON, LEAD, LINKISH, TITLE } from "./styles";

const DANGER_HOVER = "hover:text-destructive-ink";

function SettingsSection({ membership }: { membership: Membership }) {
	const update = useUpdateOrganisation(membership.organisation.id);
	const save = async (input: OrganisationInput) => {
		await update.mutateAsync(input);
		toast.success("Settings saved");
	};
	return (
		<section aria-label="Settings" className="mb-8">
			<h2 className={HEADING}>
				<Settings className={HEADING_ICON} />
				Settings
			</h2>
			<Panel padding="p-5">
				<OrganisationForm
					key={membership.organisation.createdAt}
					initial={membership.organisation}
					onSave={save}
					submitLabel="Save"
				/>
			</Panel>
		</section>
	);
}

export default function Organisation() {
	const { id = "" } = useParams<{ id: string }>();
	const navigate = useNavigate();
	const membership = useMembership(id);
	const leave = useLeaveOrganisation(id);
	const { confirm, confirmDialog } = useConfirm();

	if (membership.error) {
		return (
			<div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
				<Panel role="alert" padding="px-6 py-[22px]">
					<p className="font-heading text-lg font-extrabold text-foreground">
						You're not a member of this organisation.
					</p>
					<p className={cn(LEAD, "mt-1")}>
						If you were, your own hours on its projects are still yours to read.
					</p>
					<Link to={`/organisations/${id}/archive`} className={`${LINKISH} mt-3 inline-block`}>
						Your hours
					</Link>
				</Panel>
			</div>
		);
	}
	const data = membership.data;
	if (!data) return <p className="text-sm text-muted-foreground px-6 py-6">Loading…</p>;

	const org = data.organisation;
	const admin = canAdminister(data.role);

	const leaveNow = async () => {
		const ok = await confirm({
			title: `Leave ${org.name}?`,
			detail: `Tracking to its projects stops and they leave your list. ${org.name} keeps its working-time record of your hours so far, and you keep a read-only archive of them.`,
			confirmLabel: "Leave",
			cancelLabel: "Stay",
		});
		if (!ok) return;
		leave.mutate(undefined, {
			onSuccess: () => {
				toast.success(`You left ${org.name}`);
				navigate("/organisations");
			},
			// 409 LAST_OWNER: the API's detail says to hand the organisation on first.
			onError: (err) => toast.error(describeError(err, "You could not leave.")),
		});
	};

	return (
		<div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 pb-24">
			<header className="flex items-center gap-3 flex-wrap mb-8">
				<OrganisationMark name={org.name} logoUrl={org.logoUrl} size="md" tileOnly />
				<h1 className={TITLE}>{org.name}</h1>
				<span className="text-sm font-medium text-foreground/90">{ROLE_LABELS[data.role]}</span>
				{admin && (
					<Link to={`/organisations/${id}/record`} className={`${LINKISH} ml-auto`}>
						This month's record
					</Link>
				)}
			</header>

			<section aria-label={`What ${org.name} can see`} className="mb-8">
				<h2 className={HEADING}>
					<Eye className={HEADING_ICON} />
					What {org.name} can see
				</h2>
				<Panel padding="p-5" className="space-y-2.5">
					<p className="text-[13px] leading-normal font-medium text-foreground">
						On its own projects, {org.name} sees your finished entries — start, end, duration and
						the note — and your absences as a date, a type and whether it was a half day. Where you
						have a contract on one, it sees the balance.
					</p>
					<p className="text-[13px] leading-normal font-medium text-foreground">
						It never sees your flow scores, apps, repositories or idle time; your biometrics, the
						coach, your calendar or insights; your tags; or any personal project. Nothing about now
						crosses: a running timer is not in its figures.
					</p>
					<Link to={`/organisations/${id}/visible`} className={LINKISH}>
						See the actual data
					</Link>
				</Panel>
			</section>

			{admin && (
				<>
					<MembersSection organisationId={id} />
					<InvitesSection organisationId={id} />
					<JoinRequestsSection organisationId={id} />
					<ProjectsSection organisationId={id} />
					<SettingsSection membership={data} />
				</>
			)}

			<section aria-label="Leave" className="mb-8">
				<h2 className={HEADING}>
					<LogOut className={HEADING_ICON} />
					Leave
				</h2>
				<Panel padding="p-5" className="flex items-start gap-3 flex-wrap">
					<p className={cn(LEAD, "flex-1 min-w-[200px]")}>
						Tracking to {org.name}'s projects stops, it keeps its working-time record, and a
						read-only archive of your hours remains.
					</p>
					<Button
						type="button"
						variant="secondary"
						size="sm"
						className={DANGER_HOVER}
						onClick={() => void leaveNow()}
						disabled={leave.isPending}
					>
						<Building2 aria-hidden="true" />
						Leave {org.name}
					</Button>
				</Panel>
			</section>
			{confirmDialog}
		</div>
	);
}
