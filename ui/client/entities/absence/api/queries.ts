/**
 * Absence TanStack Query Hooks
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Absence } from "../model";
import {
	type AbsenceInput,
	type AbsenceRange,
	deleteAbsence,
	fetchAbsences,
	recordAbsence,
} from "./absenceApi";

export const absenceKeys = {
	all: ["absences"] as const,
	project: (projectId: string) => [...absenceKeys.all, projectId] as const,
	range: (projectId: string, range: AbsenceRange) =>
		[...absenceKeys.project(projectId), range.start, range.end] as const,
};

/** The project's absences with a date in [start, end]. */
export function useAbsences(projectId: string | undefined, range: AbsenceRange) {
	return useQuery({
		queryKey: absenceKeys.range(projectId || "", range),
		queryFn: (): Promise<Absence[]> => fetchAbsences(projectId as string, range),
		enabled: !!projectId,
		staleTime: 60_000,
	});
}

/**
 * An absence changes what the contract expects of the week; once something
 * reads that (Phase 5's week card), a write must invalidate it too. Today
 * only the calendar reads absences.
 */
function useInvalidateAfterAbsenceWrite() {
	const queryClient = useQueryClient();
	return (projectId: string) =>
		queryClient.invalidateQueries({ queryKey: absenceKeys.project(projectId) });
}

export function useRecordAbsence() {
	const invalidate = useInvalidateAfterAbsenceWrite();
	return useMutation({
		mutationFn: ({ projectId, input }: { projectId: string; input: AbsenceInput }) =>
			recordAbsence(projectId, input),
		onSuccess: (_absence, { projectId }) => invalidate(projectId),
	});
}

export function useRemoveAbsence() {
	const invalidate = useInvalidateAfterAbsenceWrite();
	return useMutation({
		mutationFn: ({ projectId, absenceId }: { projectId: string; absenceId: string }) =>
			deleteAbsence(projectId, absenceId),
		onSuccess: (_void, { projectId }) => invalidate(projectId),
	});
}
