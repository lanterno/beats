/**
 * Organisation — `/organisations/:id`: one organisation and the caller's
 * standing in it (docs/organisations.md), under one tablist (the UX-refresh
 * mockup), so each role lands on the tabs that apply: People, Projects,
 * Audit and Settings for admins; Approvals for the people who decide (and,
 * read-only, a viewer); Timesheets for everyone, with the plain account of
 * what the organisation can see and — for anyone who has no Settings tab —
 * the way out. The selected tab lives in the URL (`?tab=`), an unknown
 * value reads as the first the role can see. The API resolves the caller's
 * membership first on every route here, so a 404 is "not a member", and
 * the archive is what remains of one that ended.
 */

import { Eye, LogOut, Settings } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import type { Membership, OrganisationInput, OrgRole } from "@/entities/organisation";
import {
	canAdminister,
	decides,
	OrganisationMark,
	ROLE_LABELS,
	readsRecord,
	useLeaveOrganisation,
	useMembership,
	useUpdateOrganisation,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Panel, TabPanel, Tabs, useConfirm } from "@/shared/ui";
import { AbsenceRequestsSection } from "./AbsenceRequestsSection";
import { AuditSection } from "./AuditSection";
import { InvitesSection } from "./InvitesSection";
import { JoinRequestsSection } from "./JoinRequestsSection";
import { MembersSection } from "./MembersSection";
import { MyTimesheetsSection } from "./MyTimesheetsSection";
import { OrganisationForm } from "./OrganisationForm";
import { ProjectsSection } from "./ProjectsSection";
import { HEADING, HEADING_ICON, LEAD, LINKISH, TITLE } from "./styles";
import { TeamsSection } from "./TeamsSection";
import { TimesheetsSection } from "./TimesheetsSection";

const DANGER_HOVER = "hover:text-destructive-ink";

type TabValue = "people" | "projects" | "approvals" | "timesheets" | "audit" | "settings";

/** The tabs this role can see, in order; the first is the default. */
function tabsFor(role: OrgRole): { value: TabValue; label: string }[] {
	const admin = canAdminister(role);
	const tabs: { value: TabValue; label: string }[] = [];
	if (admin) {
		tabs.push({ value: "people", label: "People" }, { value: "projects", label: "Projects" });
	}
	if (decides(role) || role === "viewer") tabs.push({ value: "approvals", label: "Approvals" });
	tabs.push({ value: "timesheets", label: "Timesheets" });
	if (admin) {
		tabs.push({ value: "audit", label: "Audit" }, { value: "settings", label: "Settings" });
	}
	return tabs;
}

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
	const [searchParams, setSearchParams] = useSearchParams();

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
	const tabs = tabsFor(data.role);
	const asked = searchParams.get("tab");
	const tab = tabs.find((t) => t.value === asked)?.value ?? tabs[0].value;
	const openTab = (value: TabValue) =>
		setSearchParams(
			(prev) => {
				const next = new URLSearchParams(prev);
				next.set("tab", value);
				return next;
			},
			{ replace: true },
		);

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

	const leaveSection = (
		<section aria-label="Leave" className="mb-8">
			<h2 className={HEADING}>
				<LogOut className={HEADING_ICON} />
				Leave
			</h2>
			<Panel padding="p-5" className="flex items-start gap-3 flex-wrap">
				<p className={cn(LEAD, "flex-1 min-w-[200px]")}>
					Tracking to {org.name}'s projects stops, it keeps its working-time record, and a read-only
					archive of your hours remains.
				</p>
				<Button
					type="button"
					variant="secondary"
					size="sm"
					className={DANGER_HOVER}
					onClick={() => void leaveNow()}
					disabled={leave.isPending}
				>
					<LogOut aria-hidden="true" />
					Leave {org.name}
				</Button>
			</Panel>
		</section>
	);

	return (
		<div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 pb-24">
			<header className="flex items-center gap-3 flex-wrap mb-8">
				<OrganisationMark name={org.name} logoUrl={org.logoUrl} size="md" tileOnly />
				<h1 className={TITLE}>{org.name}</h1>
				<span className="text-sm font-medium text-foreground/90">{ROLE_LABELS[data.role]}</span>
				{readsRecord(data.role) && (
					<Link to={`/organisations/${id}/record`} className={`${LINKISH} ml-auto`}>
						This month's record
					</Link>
				)}
			</header>

			<Tabs
				tabs={tabs}
				value={tab}
				onChange={openTab}
				label="Organisation sections"
				className="mb-8"
			/>

			{admin && (
				<TabPanel value="people" current={tab}>
					<div className="grid gap-x-6 lg:grid-cols-[3fr_2fr]">
						<div>
							<MembersSection organisationId={id} />
						</div>
						<div>
							<TeamsSection organisationId={id} />
							<InvitesSection organisationId={id} />
							<JoinRequestsSection organisationId={id} />
						</div>
					</div>
				</TabPanel>
			)}

			{admin && (
				<TabPanel value="projects" current={tab}>
					<ProjectsSection organisationId={id} role={data.role} />
				</TabPanel>
			)}

			{(decides(data.role) || data.role === "viewer") && (
				<TabPanel value="approvals" current={tab}>
					{decides(data.role) && <AbsenceRequestsSection organisationId={id} />}
					<TimesheetsSection organisationId={id} role={data.role} />
				</TabPanel>
			)}

			<TabPanel value="timesheets" current={tab}>
				<MyTimesheetsSection organisationId={id} role={data.role} />

				<section aria-label={`What ${org.name} can see`} className="mb-8">
					<h2 className={HEADING}>
						<Eye className={HEADING_ICON} />
						What {org.name} can see
					</h2>
					<Panel padding="p-5" className="space-y-2.5">
						<p className="text-[13px] leading-normal font-medium text-foreground">
							On its own projects, {org.name} sees your finished entries — start, end, duration and
							the note — and your absences as a date, a type and whether it was a half day. Where
							you have a contract on one, it sees the balance.
						</p>
						<p className="text-[13px] leading-normal font-medium text-foreground">
							It never sees your flow scores, apps, repositories or idle time; your biometrics, the
							coach, your calendar or insights; your tags; or any personal project. Nothing about
							now crosses: a running timer is not in its figures.
						</p>
						<Link to={`/organisations/${id}/visible`} className={LINKISH}>
							See the actual data
						</Link>
					</Panel>
				</section>

				{!admin && leaveSection}
			</TabPanel>

			{admin && (
				<TabPanel value="audit" current={tab}>
					<AuditSection organisationId={id} />
				</TabPanel>
			)}

			{admin && (
				<TabPanel value="settings" current={tab}>
					<SettingsSection membership={data} />
					{leaveSection}
				</TabPanel>
			)}
			{confirmDialog}
		</div>
	);
}
