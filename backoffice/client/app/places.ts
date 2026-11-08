/**
 * Where the back office goes, grouped by the job each page serves: what
 * needs the operator today, the two things they look up, the platform's
 * health, and the records only the control plane keeps. The sidebar and
 * the narrow-width strip draw the same list, so a page added here is
 * reachable at every width.
 */

import type { ComponentType } from "react";
import {
	BellIcon,
	BuildingIcon,
	ClipboardIcon,
	ClockIcon,
	DatabaseIcon,
	PersonIcon,
	ScrollIcon,
	ShieldIcon,
} from "@/shared/ui/icons";

export interface Place {
	to: string;
	label: string;
	Icon: ComponentType<{ className?: string }>;
}

export interface Group {
	/** Said over the group in the sidebar; the first group has none. */
	label?: string;
	places: Place[];
}

export const GROUPS: Group[] = [
	{ places: [{ to: "/", label: "Today", Icon: BellIcon }] },
	{
		label: "Look up",
		places: [
			{ to: "/accounts", label: "Accounts", Icon: PersonIcon },
			{ to: "/organisations", label: "Organisations", Icon: BuildingIcon },
		],
	},
	{
		label: "The platform",
		places: [
			{ to: "/trust", label: "Trust and safety", Icon: ShieldIcon },
			{ to: "/capacity", label: "Capacity", Icon: DatabaseIcon },
		],
	},
	{
		label: "Records",
		places: [
			{ to: "/jobs", label: "Jobs", Icon: ClockIcon },
			{ to: "/audit", label: "Audit", Icon: ScrollIcon },
			{ to: "/compliance", label: "Compliance", Icon: ClipboardIcon },
		],
	},
];

export const PLACES: Place[] = GROUPS.flatMap((group) => group.places);
