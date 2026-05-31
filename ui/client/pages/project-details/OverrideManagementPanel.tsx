/**
 * OverrideManagementPanel — every weekly-goal override for the project,
 * with a delete affordance per row. Lives inside ProjectSettingsDrawer so
 * users can finally see + clean up the override log that GoalOverridePopover
 * has been silently appending to.
 *
 * P3.4 of the project-management revamp. Migration policy per the open
 * question: legacy 'permanent' (effective_from) overrides stay as-is and
 * surface here for user-driven cleanup.
 */

import { Calendar, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import type { GoalOverride, Project } from "@/entities/project";
import { useUpdateGoalOverrides } from "@/entities/project";
import { describeError } from "@/shared/api";
import { formatDateOnly } from "@/shared/lib";

interface OverrideManagementPanelProps {
	project: Project;
}

function overrideKey(o: GoalOverride): string {
	// Either weekOf or effectiveFrom is set per the domain invariant. Combine
	// so the React key survives multiple overrides of the same kind on the
	// same Monday (uncommon but possible while a save is in flight).
	return `${o.weekOf ?? ""}::${o.effectiveFrom ?? ""}`;
}

function describeScope(o: GoalOverride): { label: string; date: string | null } {
	if (o.weekOf) return { label: "This week", date: o.weekOf };
	if (o.effectiveFrom) return { label: "From", date: o.effectiveFrom };
	return { label: "Unknown", date: null };
}

function describeGoal(o: GoalOverride): string {
	if (o.weeklyGoal == null) return "No goal";
	const type = o.goalType ?? "target";
	return `${o.weeklyGoal}h ${type}`;
}

export function OverrideManagementPanel({ project }: OverrideManagementPanelProps) {
	const updateOverrides = useUpdateGoalOverrides();
	const overrides = project.goalOverrides ?? [];

	if (overrides.length === 0) {
		return (
			<section className="rounded-lg border border-border/60 bg-secondary/10 p-3">
				<h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground mb-1">
					Goal overrides
				</h3>
				<p className="text-[11px] text-muted-foreground/70">
					No overrides yet. Per-week goal exceptions show up here.
				</p>
			</section>
		);
	}

	// Show one-off (week) entries first, then forward-looking (effective_from).
	const sorted = [...overrides].sort((a, b) => {
		if (a.weekOf && b.weekOf) return b.weekOf.localeCompare(a.weekOf);
		if (a.weekOf) return -1;
		if (b.weekOf) return 1;
		return (b.effectiveFrom ?? "").localeCompare(a.effectiveFrom ?? "");
	});

	const handleDelete = (target: GoalOverride) => {
		const next = overrides.filter((o) => overrideKey(o) !== overrideKey(target));
		updateOverrides.mutate(
			{
				projectId: project.id,
				overrides: next.map((o) => ({
					week_of: o.weekOf ?? null,
					effective_from: o.effectiveFrom ?? null,
					weekly_goal: o.weeklyGoal,
					goal_type: o.goalType ?? null,
					note: o.note ?? null,
				})),
			},
			{
				onSuccess: () => toast.success("Override removed"),
				onError: (err) => toast.error(describeError(err, "Failed to remove override")),
			},
		);
	};

	const pendingKey = updateOverrides.isPending && updateOverrides.variables ? "pending" : null;

	return (
		<section className="rounded-lg border border-border/60 bg-secondary/10 p-3">
			<header className="flex items-center gap-1.5 mb-2">
				<h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
					Goal overrides
				</h3>
				<span className="text-[10px] text-muted-foreground/60">({overrides.length})</span>
			</header>
			<ul className="space-y-1">
				{sorted.map((o) => {
					const scope = describeScope(o);
					return (
						<li
							key={overrideKey(o)}
							className="flex items-center gap-2 rounded-md bg-background/40 px-2 py-1.5 text-xs"
						>
							<Calendar className="w-3 h-3 text-muted-foreground/60 shrink-0" aria-hidden="true" />
							<span className="text-muted-foreground tabular-nums shrink-0">{scope.label}</span>
							<span className="text-foreground tabular-nums shrink-0">
								{formatDateOnly(scope.date)}
							</span>
							<span className="text-foreground/80 shrink-0">·</span>
							<span className="text-foreground shrink-0">{describeGoal(o)}</span>
							{o.note && (
								<span className="text-muted-foreground/70 truncate flex-1 min-w-0">· {o.note}</span>
							)}
							<button
								type="button"
								onClick={() => handleDelete(o)}
								disabled={pendingKey !== null}
								aria-label={`Remove override for ${
									scope.date ? formatDateOnly(scope.date) : scope.label
								}`}
								className="ml-auto p-1 rounded text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
							>
								{pendingKey ? (
									<Loader2 className="w-3 h-3 animate-spin" />
								) : (
									<Trash2 className="w-3 h-3" />
								)}
							</button>
						</li>
					);
				})}
			</ul>
		</section>
	);
}
