/**
 * Recurring intention templates — define per-weekday intentions once and have
 * them auto-applied to each matching day, instead of re-adding the same
 * intentions manually every morning. Surfaces /api/plans/recurring (+ /apply),
 * which had hooks but no UI.
 */

import { CalendarClock, Plus, Trash2, Zap } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
	useApplyRecurring,
	useCreateRecurringIntention,
	useDeleteRecurringIntention,
	useRecurringIntentions,
} from "@/entities/planning";
import { useProjects } from "@/entities/project";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button } from "@/shared/ui";

// days_of_week is 0=Monday … 6=Sunday, matching the API (Python weekday()).
const DAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const DEFAULT_DAYS = [0, 1, 2, 3, 4];

function formatHours(minutes: number): string {
	const hours = minutes / 60;
	return `${hours.toFixed(minutes % 60 === 0 ? 0 : 1)}h`;
}

export function RecurringIntentions() {
	const { data: templates } = useRecurringIntentions();
	const { data: projects } = useProjects();
	const createTemplate = useCreateRecurringIntention();
	const deleteTemplate = useDeleteRecurringIntention();
	const applyToday = useApplyRecurring();

	const activeProjects = (projects ?? []).filter((p) => !p.archived);
	const projectName = (id: string) => projects?.find((p) => p.id === id)?.name ?? "Unknown";
	const projectColor = (id: string) => projects?.find((p) => p.id === id)?.color ?? "#888";

	const [projectId, setProjectId] = useState("");
	const [hours, setHours] = useState("1");
	const [days, setDays] = useState<number[]>(DEFAULT_DAYS);

	const toggleDay = (d: number) =>
		setDays((prev) =>
			prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort((a, b) => a - b),
		);

	const handleAdd = () => {
		if (!projectId) {
			toast.error("Pick a project");
			return;
		}
		if (days.length === 0) {
			toast.error("Pick at least one day");
			return;
		}
		const h = Number(hours);
		if (Number.isNaN(h) || h <= 0) {
			toast.error("Hours must be a positive number");
			return;
		}
		createTemplate.mutate(
			{ project_id: projectId, planned_minutes: Math.round(h * 60), days_of_week: days },
			{
				onSuccess: () => {
					toast.success("Recurring intention added");
					setProjectId("");
					setHours("1");
					setDays(DEFAULT_DAYS);
				},
				onError: (err) => toast.error(describeError(err, "Failed to add recurring intention")),
			},
		);
	};

	const handleApply = () => {
		applyToday.mutate(undefined, {
			onSuccess: (res) =>
				toast.success(
					res.created > 0
						? `Added ${res.created} intention${res.created !== 1 ? "s" : ""} to today`
						: "Today already has these intentions",
				),
			onError: (err) => toast.error(describeError(err, "Failed to apply")),
		});
	};

	const list = templates ?? [];

	return (
		<section className="mt-8">
			<div className="flex items-center gap-2 mb-3">
				<CalendarClock className="w-4 h-4 text-accent" />
				<h2 className="text-sm font-medium text-foreground">Recurring intentions</h2>
				<Button
					type="button"
					variant="outline"
					size="sm"
					className="ml-auto"
					onClick={handleApply}
					disabled={applyToday.isPending || list.length === 0}
				>
					<Zap className="w-3.5 h-3.5" />
					Apply to today
				</Button>
			</div>
			<p className="text-xs text-muted-foreground mb-3">
				Templates that create today's intentions on the days you choose — instead of re-adding the
				same ones every morning.
			</p>

			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				{list.length > 0 ? (
					<div className="space-y-1.5">
						{list.map((t) => (
							<div key={t.id} className="flex items-center gap-2.5">
								<div
									className="w-2 h-2 rounded-full shrink-0"
									style={{ backgroundColor: projectColor(t.project_id) }}
								/>
								<span className="text-sm text-foreground truncate flex-1 min-w-0">
									{projectName(t.project_id)}
								</span>
								<span className="text-xs tabular-nums text-muted-foreground shrink-0">
									{formatHours(t.planned_minutes)}
								</span>
								<div className="flex gap-0.5 shrink-0">
									{DAY_LABELS.map((label, i) => (
										<span
											key={label}
											className={cn(
												"text-[10px] w-4 text-center rounded",
												t.days_of_week.includes(i)
													? "bg-accent/20 text-accent"
													: "text-muted-foreground/30",
											)}
										>
											{label[0]}
										</span>
									))}
								</div>
								<button
									type="button"
									onClick={() =>
										deleteTemplate.mutate(t.id, {
											onSuccess: () => toast.success("Removed"),
											onError: (err) => toast.error(describeError(err, "Failed to remove")),
										})
									}
									aria-label={`Delete recurring intention for ${projectName(t.project_id)}`}
									className="p-1 rounded text-muted-foreground/40 hover:text-destructive transition-colors shrink-0"
								>
									<Trash2 className="w-3.5 h-3.5" />
								</button>
							</div>
						))}
					</div>
				) : (
					<p className="text-xs text-muted-foreground/60 italic">No recurring intentions yet.</p>
				)}

				<div className="pt-3 border-t border-border/40 space-y-2.5">
					<div className="flex items-center gap-2">
						<select
							value={projectId}
							onChange={(e) => setProjectId(e.target.value)}
							aria-label="Project"
							className="flex-1 min-w-0 text-sm bg-secondary/50 border border-border rounded px-2 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
						>
							<option value="">Select project…</option>
							{activeProjects.map((p) => (
								<option key={p.id} value={p.id}>
									{p.name}
								</option>
							))}
						</select>
						<input
							type="number"
							min={0.5}
							step={0.5}
							value={hours}
							onChange={(e) => setHours(e.target.value)}
							aria-label="Hours"
							className="w-16 text-right text-sm tabular-nums bg-secondary/50 border border-border rounded px-2 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
						/>
						<span className="text-xs text-muted-foreground">h</span>
					</div>
					<div className="flex items-center gap-1">
						{DAY_LABELS.map((label, i) => (
							<button
								type="button"
								key={label}
								onClick={() => toggleDay(i)}
								aria-pressed={days.includes(i)}
								aria-label={label}
								className={cn(
									"text-xs w-8 py-1 rounded border transition-colors",
									days.includes(i)
										? "bg-accent/20 text-accent border-accent/40"
										: "text-muted-foreground border-border hover:bg-secondary/50",
								)}
							>
								{label}
							</button>
						))}
						<Button
							type="button"
							size="sm"
							className="ml-auto"
							onClick={handleAdd}
							disabled={createTemplate.isPending}
						>
							<Plus className="w-3.5 h-3.5" />
							Add
						</Button>
					</div>
				</div>
			</div>
		</section>
	);
}
