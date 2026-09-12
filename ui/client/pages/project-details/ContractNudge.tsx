/**
 * ContractNudge — one line at the top of a day job whose contract names no
 * holiday region (the migration creates contracts without one), with the
 * button that opens the settings drawer on the region picker. Gone once a
 * region is set.
 */

import { Info } from "lucide-react";
import type { Project } from "@/entities/project";
import { Button } from "@/shared/ui";

interface ContractNudgeProps {
	project: Project;
	onOpenSettings: () => void;
}

export function ContractNudge({ project, onOpenSettings }: ContractNudgeProps) {
	if (project.kind !== "day_job" || !project.contract || project.contract.holidayCountry) {
		return null;
	}
	return (
		<div
			role="status"
			className="mt-4 flex flex-wrap items-center gap-2 rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-xs text-foreground"
		>
			<Info className="w-3.5 h-3.5 text-accent shrink-0" aria-hidden="true" />
			<span>
				<span className="font-medium">Complete your contract</span> — set the holiday region so
				public holidays stop counting against you.
			</span>
			<Button
				type="button"
				variant="outline"
				size="sm"
				onClick={onOpenSettings}
				className="ml-auto h-7 text-xs"
			>
				Set region
			</Button>
		</div>
	);
}
