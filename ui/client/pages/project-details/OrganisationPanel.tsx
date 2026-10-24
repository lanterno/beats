/**
 * OrganisationPanel — the rail's Organisation (docs/organisations.md). On
 * an organisation's project: whose it is, since when the hours on it are
 * theirs, and where to see what they see. On a personal project of a
 * member: the offer to connect it, from a day they choose — a dialog of
 * its own on the page, not a step buried in the settings drawer. Nothing
 * for a person in no organisation, or on a project billed to a client,
 * which stays personal.
 */

import { Building2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import {
	ConnectProjectDialog,
	describeShareFrom,
	OrganisationMark,
	useMemberships,
} from "@/entities/organisation";
import type { ProjectWithDuration } from "@/entities/project";
import { Button, Panel } from "@/shared/ui";
import { LABEL, LINKISH } from "./styles";

export interface OrganisationPanelProps {
	project: ProjectWithDuration;
	todayIso: string;
	/** Billed to a client: the API refuses to connect it, so nothing is offered. */
	billed?: boolean;
}

export function OrganisationPanel({ project, todayIso, billed = false }: OrganisationPanelProps) {
	const { data: memberships } = useMemberships();
	const [connecting, setConnecting] = useState(false);
	const active = (memberships ?? []).filter((m) => m.leftAt === undefined);
	const organisation = project.organisation;

	if (organisation) {
		return (
			<Panel role="region" aria-label="Organisation" padding="px-6 py-5">
				<p className={LABEL}>Organisation</p>
				<div className="mt-2 flex items-center gap-2">
					<OrganisationMark name={organisation.name} logoUrl={organisation.logoUrl} size="md" />
				</div>
				<p className="mt-1.5 text-[12.5px] font-medium text-muted-foreground leading-normal">
					{organisation.name} owns this project and sees your hours on it{" "}
					{describeShareFrom(organisation.sharedFrom)}. Your goal, local repo paths and contract
					stay yours.
				</p>
				<div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
					<Link to={`/organisations/${organisation.id}/visible`} className={LINKISH}>
						What {organisation.name} can see
					</Link>
					<Link to={`/organisations/${organisation.id}`} className={LINKISH}>
						Open {organisation.name}
					</Link>
				</div>
			</Panel>
		);
	}

	if (active.length === 0 || billed || project.archived) return null;

	const only = active.length === 1 ? active[0].organisation.name : null;
	return (
		<Panel role="region" aria-label="Organisation" padding="px-6 py-5">
			<p className={LABEL}>Organisation</p>
			<p className="mt-2 text-[12.5px] font-medium text-muted-foreground leading-normal">
				Yours alone. Connecting it makes its hours part of an organisation's working-time record,
				from a day you choose.
			</p>
			<Button
				type="button"
				variant="secondary"
				size="sm"
				className="mt-3"
				onClick={() => setConnecting(true)}
			>
				<Building2 aria-hidden="true" />
				{only ? `Connect to ${only}…` : "Connect to an organisation…"}
			</Button>
			{connecting && (
				<ConnectProjectDialog
					project={{ id: project.id, name: project.name }}
					memberships={active}
					todayIso={todayIso}
					onConnected={() => setConnecting(false)}
					onClose={() => setConnecting(false)}
				/>
			)}
		</Panel>
	);
}
