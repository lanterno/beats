/**
 * ProjectHeader — the identity line on the sky: dot, name, a derived kind
 * chip, description, repo, the Archived chip with its inline Restore, the
 * gear. No figures (the mockup's "the header identifies and never
 * measures"): everything that could disagree with the standing below left.
 */

import { Loader2, Settings } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import type { ProjectFormAutoFocusField, ProjectWithDuration } from "@/entities/project";
import {
	assignColor,
	displayTermOn,
	standingGoalOn,
	termHoursPerWeek,
	toPercent,
	useUnarchiveProject,
	useUpdateProject,
} from "@/entities/project";
import { describeError } from "@/shared/api";
import { cn, mondayOfIso } from "@/shared/lib";
import { ColorPicker } from "@/shared/ui";
import { plainDate } from "./dates";
import { ProjectGitHubBadge } from "./ProjectGitHubBadge";

interface ProjectHeaderProps {
	project: ProjectWithDuration;
	todayIso: string;
	onOpenSettings: (field: ProjectFormAutoFocusField) => void;
}

function hoursLabel(hours: number): string {
	return `${Math.round(hours * 100) / 100} h`;
}

/**
 * "Day job · 80% of 42 h · CH-ZH", "Day job · no contract", "Day job ·
 * objective", "Day job · ended Aug 31, 2026", "Side project · goal 8 h/week",
 * "Freelance" — what the project is, read off its kind and contract today.
 * Off a day job the goal is the one in force this week, as the Goal panel
 * reads it: a permanent override, else the project's own.
 */
export function kindChip(
	project: Pick<
		ProjectWithDuration,
		"kind" | "contract" | "weeklyGoal" | "goalType" | "goalOverrides"
	>,
	todayIso: string,
): string {
	if (project.kind === "day_job") {
		const contract = project.contract;
		if (!contract) return "Day job · no contract";
		if (contract.endedOn && contract.endedOn <= todayIso) {
			return `Day job · ended ${plainDate(contract.endedOn)}`;
		}
		const term = displayTermOn(contract, todayIso);
		if (!term) return "Day job · no contract";
		const region = contract.holidayCountry
			? ` · ${contract.holidayCountry}${contract.holidaySubdivision ? `-${contract.holidaySubdivision}` : ""}`
			: "";
		if (term.scheduleType === "objective") return `Day job · objective${region}`;
		const weekly = termHoursPerWeek(term);
		if (
			term.scheduleType === "part_time" &&
			term.fullTimeHours != null &&
			term.percentage != null
		) {
			return `Day job · ${toPercent(term.percentage)}% of ${hoursLabel(term.fullTimeHours)}${region}`;
		}
		if (term.scheduleType === "full_time") {
			return `Day job · Full time${weekly == null ? "" : ` · ${hoursLabel(weekly)}`}${region}`;
		}
		return `Day job${weekly == null ? "" : ` · ${hoursLabel(weekly)}/week`}${region}`;
	}
	const label = project.kind === "freelance" ? "Freelance" : "Side project";
	const { weeklyGoal, goalType } = standingGoalOn(project, mondayOfIso(todayIso));
	if (weeklyGoal == null) return label;
	return `${label} · ${goalType === "cap" ? "cap" : "goal"} ${hoursLabel(weeklyGoal)}/week`;
}

// `.hdr .chip` — the panel at 82 % with ink on it, so it reads on the sky.
const SKY_CHIP =
	"inline-flex items-center gap-1.5 rounded-full bg-sidebar px-[11px] py-[3px] text-xs font-bold text-foreground whitespace-nowrap";

const FOCUS = "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

export function ProjectHeader({ project, todayIso, onOpenSettings }: ProjectHeaderProps) {
	const navigate = useNavigate();
	const [colorPickerOpen, setColorPickerOpen] = useState(false);
	const updateProject = useUpdateProject();
	const unarchive = useUnarchiveProject();

	const handleRestore = () => {
		unarchive.mutate(project.id, {
			onSuccess: () => toast.success("Project restored"),
			onError: (err) => toast.error(describeError(err, "Failed to restore project")),
		});
	};

	return (
		<header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-2 pt-1.5 pb-[18px]">
			<div className="relative">
				<button
					type="button"
					onClick={() => setColorPickerOpen((o) => !o)}
					className={cn(
						"block w-3.5 h-3.5 rounded-full shrink-0 shadow-[0_0_0_3px_hsl(var(--card)/.6)] hover:scale-110 transition-transform",
						FOCUS,
					)}
					style={{ backgroundColor: project.color || assignColor(project.id) }}
					title="Change colour"
					aria-label="Change colour"
				/>
				{colorPickerOpen && (
					<ColorPicker
						value={project.color || assignColor(project.id)}
						onChange={(color) => {
							updateProject.mutate({
								id: project.id,
								name: project.name,
								description: project.description,
								color,
								archived: project.archived,
								weekly_goal: project.weeklyGoal,
								goal_type: project.goalType,
							});
						}}
						onClose={() => setColorPickerOpen(false)}
					/>
				)}
			</div>

			<button
				type="button"
				onClick={() => onOpenSettings("name")}
				className={cn(
					"font-heading text-[30px] font-extrabold tracking-[-0.02em] leading-[1.1] text-foreground text-left text-balance hover:text-accent-ink transition-colors rounded-lg",
					FOCUS,
				)}
				title="Edit project"
			>
				{project.name}
			</button>

			<span className={SKY_CHIP}>{kindChip(project, todayIso)}</span>

			{project.description ? (
				<button
					type="button"
					onClick={() => onOpenSettings("description")}
					className={cn(
						"text-sm font-medium text-foreground/90 truncate max-w-[32ch] text-left hover:text-foreground transition-colors rounded",
						FOCUS,
					)}
					title="Edit description"
				>
					{project.description}
				</button>
			) : (
				<button
					type="button"
					onClick={() => onOpenSettings("description")}
					className={cn(
						// Ink at 90 %: the sky's top is the palest ground on the page (/55 was 2.5:1).
						"text-sm font-medium text-foreground/90 hover:text-foreground transition-colors rounded",
						FOCUS,
					)}
				>
					+ Add description
				</button>
			)}

			<ProjectGitHubBadge
				githubRepo={project.githubRepo}
				onConfigureRepo={() => onOpenSettings("githubRepo")}
				onConnectGitHub={() => navigate("/settings#github")}
			/>

			{project.archived && (
				<span
					className="inline-flex items-center gap-2 rounded-full bg-destructive/20 px-[11px] py-[3px] text-xs font-bold text-destructive whitespace-nowrap"
					title="This project is archived. Hidden from active pickers and lists."
				>
					Archived
					<button
						type="button"
						onClick={handleRestore}
						disabled={unarchive.isPending}
						className={cn(
							"inline-flex items-center gap-1 underline underline-offset-[3px] disabled:opacity-50",
							FOCUS,
						)}
					>
						{unarchive.isPending && <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />}
						Restore
					</button>
				</span>
			)}

			<button
				type="button"
				onClick={() => onOpenSettings("name")}
				aria-label="Project settings"
				title="Project settings"
				className={cn(
					"ml-auto grid place-items-center w-[34px] h-[34px] rounded-full bg-sidebar text-foreground hover:bg-card transition-colors",
					FOCUS,
				)}
			>
				<Settings className="w-4 h-4" aria-hidden="true" />
			</button>
		</header>
	);
}
