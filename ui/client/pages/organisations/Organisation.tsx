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
 *
 * The title, the role chip, the tablist and the page's destinations — the
 * record, and one's own archive — sit together in a page bar (the mockup's
 * `.pagebar`), a Panel: the sky is the least readable surface the app has,
 * and nothing a page is read by belongs on it.
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
	useAbsenceRequests,
	useJoinRequests,
	useLeaveOrganisation,
	useMembers,
	useMembership,
	useTimesheets,
	useUpdateOrganisation,
} from "@/entities/organisation";
import { ApiError, describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Chip, Panel, TabPanel, Tabs, useConfirm } from "@/shared/ui";
import { AbsenceRequestsSection } from "./AbsenceRequestsSection";
import { AuditSection } from "./AuditSection";
import { ClosingSection } from "./ClosingSection";
import { InvitesSection } from "./InvitesSection";
import { JoinRequestsSection } from "./JoinRequestsSection";
import { MembersSection } from "./MembersSection";
import { MyTimesheetsSection } from "./MyTimesheetsSection";
import { OrganisationForm } from "./OrganisationForm";
import { ProjectsSection } from "./ProjectsSection";
import { Section } from "./Section";
import { CRUMB, DANGER_HOVER, LEAD, LINKISH, PAGE, PAGE_TITLE, PAGEBAR } from "./styles";
import { TeamsSection } from "./TeamsSection";
import { TimesheetsSection } from "./TimesheetsSection";

export type TabValue = "people" | "projects" | "approvals" | "timesheets" | "audit" | "settings";

/**
 * The tabs this role can see, in order; the first is the default. The index
 * page reads the same list to deep-link its cards, so what a card offers and
 * what the page then shows cannot drift apart.
 */
export function tabsFor(role: OrgRole): { value: TabValue; label: string }[] {
	const admin = canAdminister(role);
	const tabs: { value: TabValue; label: string }[] = [];
	if (admin) {
		tabs.push({ value: "people", label: "People" }, { value: "projects", label: "Projects" });
	}
	if (readsRecord(role)) tabs.push({ value: "approvals", label: "Approvals" });
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
		<Section label="Settings" icon={Settings} bodyClassName="p-5">
			<OrganisationForm
				// Keyed on the stored values: a save by another admin remounts
				// the form with them, while typing (local state) never does.
				// `createdAt` was the key before — a constant, so the form held
				// stale values past any refetch.
				key={[
					membership.organisation.name,
					membership.organisation.logoUrl,
					membership.organisation.weekStart,
					membership.organisation.timezone,
					membership.organisation.holidayCountry,
					membership.organisation.holidaySubdivision,
				].join("|")}
				initial={membership.organisation}
				onSave={save}
				submitLabel="Save"
			/>
		</Section>
	);
}

export default function Organisation() {
	const { id = "" } = useParams<{ id: string }>();
	const navigate = useNavigate();
	const membership = useMembership(id);
	const leave = useLeaveOrganisation(id);
	// The last owner may not leave (409 LAST_OWNER), so an owner is told
	// before trying rather than after. Only an owner can be the last one, so
	// nobody else pays for the read.
	const owners = useMembers(id, { enabled: membership.data?.role === "owner" });
	// What the tabs wear as counts: work waiting on the caller. The sections
	// read the same queries, so an open tab costs nothing twice.
	const role = membership.data?.role;
	const waitingRequests = useJoinRequests(id, { enabled: role ? canAdminister(role) : false });
	const waitingAbsences = useAbsenceRequests(id, {
		pending: true,
		enabled: role ? decides(role) : false,
	});
	const allSheets = useTimesheets(id, { enabled: role ? decides(role) : false });
	const { confirm, confirmDialog } = useConfirm();
	const [searchParams, setSearchParams] = useSearchParams();

	if (membership.error) {
		// Only a 404 is "not a member" — the API resolves the membership
		// first on every route here. Anything else is the read failing, and
		// sending someone to their archive over a 500 would be a lie.
		const notAMember = membership.error instanceof ApiError && membership.error.isNotFound();
		return (
			<div className={PAGE}>
				<Panel role="alert" padding="px-6 py-[22px]">
					<p className="font-heading text-lg font-extrabold text-foreground">
						{notAMember
							? "You're not a member of this organisation."
							: "This organisation couldn't be loaded."}
					</p>
					<p className={cn(LEAD, "mt-1")}>
						{notAMember
							? "If you were, your own hours on its projects are still yours to read."
							: describeError(membership.error, "The read failed. It may be a connection.")}
					</p>
					{notAMember ? (
						<Link to={`/organisations/${id}/archive`} className={`${LINKISH} mt-3 inline-block`}>
							Your hours
						</Link>
					) : (
						<Button
							type="button"
							variant="secondary"
							size="sm"
							className="mt-3"
							onClick={() => void membership.refetch()}
							disabled={membership.isFetching}
						>
							{membership.isFetching ? "Trying…" : "Try again"}
						</Button>
					)}
				</Panel>
			</div>
		);
	}
	const data = membership.data;
	if (!data) {
		return (
			<div className={PAGE}>
				<Panel padding="px-5 py-3" className={PAGEBAR}>
					<p className={LEAD}>Loading…</p>
				</Panel>
			</div>
		);
	}

	const org = data.organisation;
	const admin = canAdminister(data.role);
	const waiting = {
		people: waitingRequests.data?.length ?? 0,
		approvals:
			(waitingAbsences.data?.length ?? 0) +
			(allSheets.data?.filter((s) => s.status === "submitted").length ?? 0),
	};
	const tabs = tabsFor(data.role).map((t) =>
		t.value === "people" || t.value === "approvals" ? { ...t, count: waiting[t.value] } : t,
	);
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

	// Undefined while the roster is still coming: Leave stays live rather
	// than flickering disabled on every load.
	const soleOwner =
		data.role === "owner" && owners.data
			? owners.data.filter((m) => m.role === "owner" && !m.leftAt).length <= 1
			: false;

	const leaveSection = (
		<Section
			label="Leave"
			icon={LogOut}
			bodyClassName="p-5"
			action={
				<Button
					type="button"
					variant="secondary"
					size="sm"
					className={DANGER_HOVER}
					onClick={() => void leaveNow()}
					disabled={leave.isPending || soleOwner}
				>
					<LogOut aria-hidden="true" />
					Leave {org.name}
				</Button>
			}
		>
			<p className={LEAD}>
				{soleOwner ? (
					<>
						You are {org.name}'s only owner, and an organisation is never left without one. Make
						someone else an owner in{" "}
						<button type="button" onClick={() => openTab("people")} className={LINKISH}>
							People
						</button>{" "}
						first.
					</>
				) : (
					<>
						Tracking to {org.name}'s projects stops, it keeps its working-time record, and a
						read-only archive of your hours remains.
					</>
				)}
			</p>
		</Section>
	);

	return (
		<div className={PAGE}>
			<Panel padding="px-5 py-3" className={PAGEBAR}>
				<OrganisationMark name={org.name} logoUrl={org.logoUrl} size="md" tileOnly />
				<div className="min-w-0">
					<Link to="/organisations" className={CRUMB}>
						Organisations
					</Link>
					<h1 className={cn(PAGE_TITLE, "truncate")}>{org.name}</h1>
				</div>
				{/* A role is not a state: the neutral wash, never ok/warn/bad. */}
				<Chip>{ROLE_LABELS[data.role]}</Chip>
				<Tabs
					tabs={tabs}
					value={tab}
					onChange={openTab}
					label="Organisation sections"
					className="ml-auto"
				/>
				{readsRecord(data.role) && (
					<Link to={`/organisations/${id}/record`} className={`${LINKISH} whitespace-nowrap`}>
						This month's record
					</Link>
				)}
				<Link
					to={`/organisations/${id}/archive`}
					className={`${LINKISH} whitespace-nowrap`}
					aria-label="Your hours in this organisation"
				>
					Your hours
				</Link>
			</Panel>

			{org.closesOn && (
				<Panel role="status" padding="px-6 py-[18px]">
					<p className="font-heading text-[15px] font-extrabold text-foreground">
						{org.name} closes on {org.closesOn}.
					</p>
					<p className={cn(LEAD, "mt-1")}>
						Your hours stay yours: each of its projects comes back to you as your own when it
						closes. Take{" "}
						<Link to={`/organisations/${id}/archive`} className={LINKISH}>
							your archive's CSV
						</Link>{" "}
						if you want a copy
						{readsRecord(data.role) && (
							<>
								{" "}
								— and the organisation's own copy is{" "}
								<Link to={`/organisations/${id}/record`} className={LINKISH}>
									the record's CSVs
								</Link>
								, which do not survive the closing
							</>
						)}
						.
					</p>
				</Panel>
			)}

			{admin && (
				<TabPanel value="people" current={tab}>
					<div className="grid gap-4 items-start lg:grid-cols-[minmax(0,3fr)_minmax(320px,2fr)]">
						<div>
							<MembersSection organisationId={id} role={data.role} userId={data.userId} />
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
					<ProjectsSection organisationId={id} />
				</TabPanel>
			)}

			{readsRecord(data.role) && (
				<TabPanel value="approvals" current={tab}>
					<div className="grid gap-4 items-start xl:grid-cols-2">
						{decides(data.role) && <AbsenceRequestsSection organisationId={id} />}
						<TimesheetsSection organisationId={id} role={data.role} userId={data.userId} />
						{/* A manager's scope is their teams, which only the admin tab
						    listed; read-only here, so they can see whose months and
						    days are theirs to decide. */}
						{!admin && <TeamsSection organisationId={id} readOnly />}
					</div>
				</TabPanel>
			)}

			<TabPanel value="timesheets" current={tab}>
				<div className="grid gap-4 items-start lg:grid-cols-[minmax(0,3fr)_minmax(320px,2fr)]">
					<MyTimesheetsSection organisationId={id} userId={data.userId} timezone={org.timezone} />

					<div>
						<Section
							label={`What ${org.name} can see`}
							title={`What ${org.name} can see`}
							icon={Eye}
							bodyClassName="p-5 space-y-2.5"
							action={
								<Link to={`/organisations/${id}/visible`} className={LINKISH}>
									See the actual data
								</Link>
							}
						>
							<p className="text-[13px] leading-normal font-medium text-foreground">
								On its own projects, {org.name} sees your finished entries — start, end, duration
								and the note — and your absences as a date, a type and whether it was a half day.
								Where you have a contract on one, it sees the balance.
							</p>
							<p className="text-[13px] leading-normal font-medium text-foreground">
								It never sees your flow scores, apps, repositories or idle time; your biometrics,
								the coach, your calendar or insights; your tags; or any personal project. Nothing
								about now crosses: a running timer is not in its figures.
							</p>
						</Section>

						{!admin && leaveSection}
					</div>
				</div>
			</TabPanel>

			{admin && (
				<TabPanel value="audit" current={tab}>
					<AuditSection organisationId={id} />
				</TabPanel>
			)}

			{admin && (
				<TabPanel value="settings" current={tab}>
					<SettingsSection membership={data} />
					{data.role === "owner" && <ClosingSection organisation={org} />}
					{leaveSection}
				</TabPanel>
			)}
			{confirmDialog}
		</div>
	);
}
