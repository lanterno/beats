/**
 * ProjectIntentionStrip — near-the-header surface that brings today's
 * intention for this project (if any) + the recurring template (if any)
 * onto the project's own page. Pre-P4.2 this state lived only on the
 * Plan page; the project page never reflected what the user had committed
 * to today.
 *
 * Zero-states surface the CTAs that move the user toward Plan.
 */

import { CalendarClock, ExternalLink, Target } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useIntentions, useRecurringIntentions, useUpdateIntention } from "@/entities/planning";
import { describeError } from "@/shared/api";
import { cn, formatDuration } from "@/shared/lib";

interface ProjectIntentionStripProps {
	projectId: string;
	projectName: string;
}

const DAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

function todayIso(): string {
	const d = new Date();
	const yyyy = d.getFullYear();
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	return `${yyyy}-${mm}-${dd}`;
}

export function ProjectIntentionStrip({ projectId, projectName }: ProjectIntentionStripProps) {
	const today = todayIso();
	const { data: intentions } = useIntentions(today);
	const { data: recurring } = useRecurringIntentions();
	const updateIntention = useUpdateIntention();

	const todaysIntention = (intentions ?? []).find((i) => i.project_id === projectId) ?? null;
	const recurringTemplate = (recurring ?? []).find((r) => r.project_id === projectId) ?? null;

	const hasAnything = todaysIntention || recurringTemplate;

	const toggleComplete = () => {
		if (!todaysIntention) return;
		updateIntention.mutate(
			{
				intentionId: todaysIntention.id,
				updates: { completed: !todaysIntention.completed },
			},
			{
				onError: (err) => toast.error(describeError(err, "Failed to update intention")),
			},
		);
	};

	if (!hasAnything) {
		return (
			<section
				aria-label={`Intentions for ${projectName}`}
				className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-border/60 bg-card/40 px-3 py-2 text-xs text-muted-foreground"
			>
				<Target className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" aria-hidden="true" />
				<span>No intention set today.</span>
				<Link
					to="/plan"
					className="inline-flex items-center gap-1 text-accent hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
				>
					Plan one
					<ExternalLink className="w-3 h-3" aria-hidden="true" />
				</Link>
				<span aria-hidden="true">·</span>
				<Link
					to="/plan"
					className="inline-flex items-center gap-1 text-accent hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
				>
					Set a recurring intention
					<ExternalLink className="w-3 h-3" aria-hidden="true" />
				</Link>
			</section>
		);
	}

	return (
		<section
			aria-label={`Intentions for ${projectName}`}
			className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-border/60 bg-card px-3 py-2 text-xs"
		>
			{todaysIntention ? (
				<div className="flex items-center gap-2">
					<Target className="w-3.5 h-3.5 text-accent shrink-0" aria-hidden="true" />
					<span className="uppercase tracking-[0.12em] text-muted-foreground">Today</span>
					<label className="flex items-center gap-1.5 text-foreground">
						<input
							type="checkbox"
							checked={todaysIntention.completed}
							onChange={toggleComplete}
							disabled={updateIntention.isPending}
							aria-label={`Mark ${projectName} intention ${
								todaysIntention.completed ? "incomplete" : "complete"
							}`}
							className="cursor-pointer"
						/>
						<span
							className={cn(
								"tabular-nums",
								todaysIntention.completed && "line-through text-muted-foreground",
							)}
						>
							{formatDuration(todaysIntention.planned_minutes)}
						</span>
					</label>
				</div>
			) : (
				<div className="flex items-center gap-2 text-muted-foreground">
					<Target className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" aria-hidden="true" />
					<span>No intention today</span>
					<Link
						to="/plan"
						className="inline-flex items-center gap-1 text-accent hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
					>
						Plan one
						<ExternalLink className="w-3 h-3" aria-hidden="true" />
					</Link>
				</div>
			)}

			{recurringTemplate ? (
				<div className="flex items-center gap-2 ml-auto">
					<CalendarClock
						className="w-3.5 h-3.5 text-muted-foreground/70 shrink-0"
						aria-hidden="true"
					/>
					<span className="uppercase tracking-[0.12em] text-muted-foreground">Recurring</span>
					<div className="flex gap-0.5" role="group" aria-label="Active weekdays">
						{DAY_LABELS.map((label, i) => (
							<span
								key={label}
								className={cn(
									"text-[10px] w-4 text-center rounded",
									recurringTemplate.days_of_week.includes(i)
										? "bg-accent/20 text-accent"
										: "text-muted-foreground/30",
								)}
							>
								{label[0]}
							</span>
						))}
					</div>
					<span className="text-foreground tabular-nums">
						{formatDuration(recurringTemplate.planned_minutes)}
					</span>
					<Link
						to="/plan"
						className="inline-flex items-center gap-1 text-accent hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
					>
						Edit
						<ExternalLink className="w-3 h-3" aria-hidden="true" />
					</Link>
				</div>
			) : (
				<Link
					to="/plan"
					className="ml-auto inline-flex items-center gap-1 text-accent hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
				>
					Set a recurring intention
					<ExternalLink className="w-3 h-3" aria-hidden="true" />
				</Link>
			)}
		</section>
	);
}
