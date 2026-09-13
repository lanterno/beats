/**
 * Absence TanStack Query Hooks
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { projectKeys } from "@/entities/project";
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
 * An absence changes what the contract expects of the week, so a write
 * invalidates what reads that beside the calendar: the project's weeks
 * against the contract (the week card), the ledger (its expectation, notes
 * and every closing balance after the day) and the project list,
 * whose `this_week` include carries the same figures for the index. The
 * list's detail copy (`useProject`) is not refetched — nothing on the
 * project page reads the contract fields from it — and the holidays do not
 * move with an absence.
 */
function useInvalidateAfterAbsenceWrite() {
	const queryClient = useQueryClient();
	return (projectId: string) =>
		Promise.all([
			queryClient.invalidateQueries({ queryKey: absenceKeys.project(projectId) }),
			queryClient.invalidateQueries({ queryKey: projectKeys.contractWeeks(projectId) }),
			queryClient.invalidateQueries({ queryKey: projectKeys.ledger(projectId) }),
			queryClient.invalidateQueries({ queryKey: projectKeys.list() }),
		]);
}

/** How far a run of writes got: `done` landed, and `error` (null when none) stopped the rest. */
interface AbsenceWrites {
	done: number;
	error: unknown;
}

/**
 * The writes in order, the first failure ending the run; nothing is rolled
 * back. Each write is tried twice, as the app's mutations are — the run
 * itself is never retried, since that would repeat what already landed.
 */
async function inOrder<T>(
	items: T[],
	write: (item: T) => Promise<unknown>,
): Promise<AbsenceWrites> {
	let done = 0;
	for (const item of items) {
		try {
			await write(item).catch(() => write(item));
		} catch (error) {
			return { done, error };
		}
		done += 1;
	}
	return { done, error: null };
}

/**
 * Record a run of absences, one day after another — the API takes one
 * absence per POST, and posting on a day already booked replaces it. The
 * reads are invalidated once, when the run is over: per day they refetched
 * under the open dialog and held the next write until they had.
 */
export function useRecordAbsences() {
	const invalidate = useInvalidateAfterAbsenceWrite();
	return useMutation({
		mutationFn: ({ projectId, inputs }: { projectId: string; inputs: AbsenceInput[] }) =>
			inOrder(inputs, (input) => recordAbsence(projectId, input)),
		onSettled: (_writes, _error, { projectId }) => invalidate(projectId),
		retry: false,
	});
}

/** Remove a run of absences by id, one after another, invalidating once at the end. */
export function useRemoveAbsences() {
	const invalidate = useInvalidateAfterAbsenceWrite();
	return useMutation({
		mutationFn: ({ projectId, absenceIds }: { projectId: string; absenceIds: string[] }) =>
			inOrder(absenceIds, (absenceId) => deleteAbsence(projectId, absenceId)),
		onSettled: (_writes, _error, { projectId }) => invalidate(projectId),
		retry: false,
	});
}
