/**
 * Planning TanStack Query hooks
 */
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWeeklyPlan, upsertWeeklyPlan } from "./planningApi";

export const planningKeys = {
	all: ["planning"] as const,
	weeklyPlan: (weekOf: string) => [...planningKeys.all, "weekly-plan", weekOf] as const,
};

// Weekly Plans

export function useWeeklyPlan(weekOf: string) {
	return useQuery({
		queryKey: planningKeys.weeklyPlan(weekOf),
		queryFn: () => fetchWeeklyPlan(weekOf),
	});
}

/**
 * Hook to fetch planned hours for ONE project across MANY weeks.
 *
 * Returns a Map keyed by mondayIso → planned_hours for the project, with
 * `undefined` meaning "no plan entry for that project that week" (the
 * P4.1 spec distinguishes em-dash for absent vs '0h' for explicit-zero).
 * useQueries parallelizes the per-week fetches and reuses the
 * planningKeys.weeklyPlan cache so other consumers (PlanPage) don't
 * pay twice.
 */
export function useProjectPlannedByWeek(
	projectId: string | undefined,
	mondayIsoList: string[],
): { byMondayIso: Map<string, number>; isLoading: boolean } {
	const results = useQueries({
		queries: mondayIsoList.map((monday) => ({
			queryKey: planningKeys.weeklyPlan(monday),
			queryFn: () => fetchWeeklyPlan(monday),
			staleTime: 60_000,
			enabled: Boolean(projectId),
		})),
	});

	const byMondayIso = new Map<string, number>();
	let isLoading = false;
	results.forEach((q, i) => {
		if (q.isLoading) isLoading = true;
		const monday = mondayIsoList[i];
		const entry = q.data?.budgets.find((b) => b.project_id === projectId);
		if (entry) byMondayIso.set(monday, entry.planned_hours);
	});
	return { byMondayIso, isLoading };
}

export function useUpsertWeeklyPlan() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (args: {
			weekOf: string;
			budgets: Array<{ project_id: string; planned_hours: number }>;
		}) => upsertWeeklyPlan(args.weekOf, args.budgets),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}
