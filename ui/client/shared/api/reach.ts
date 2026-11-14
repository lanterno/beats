/**
 * Whether the server can be reached, read off a query's own retry state.
 *
 * A page that draws nothing without one read — the dashboard without the
 * projects, the sidebar's totals without the beats — used to show its spinner
 * for as long as that read had no data, which with the API down was for ever:
 * the read gave up, the page drew its panels, a panel mounting asked again, and
 * the spinner came back. Such a read retries for as long as the server cannot
 * be reached (`retryWhileUnreachable`), with TanStack's own back-off spacing the
 * tries out to one every 30 seconds, and the page says so (`waitingFor`). A read
 * paused by the browser being offline resumes by itself when the network does.
 */
import { ApiError } from "./client";

/** What a gateway answers when the service behind it did not. */
const NO_ANSWER = new Set([502, 503, 504]);

/**
 * Whether a failed call never got an answer from the API: the network failed
 * (fetch throws a TypeError), or whatever stands in front of the API answered
 * in its place — a 502, 503 or 504 without the API's error envelope. The API's
 * own refusals carry a `code`, a 500 or a 503 included, and are answers.
 */
export function isUnreachable(error: unknown): boolean {
	if (error instanceof TypeError) return true;
	return error instanceof ApiError && NO_ANSWER.has(error.statusCode) && !error.code;
}

/**
 * The retry policy of a read a page cannot draw without: keep trying while the
 * server cannot be reached, and otherwise give up after two retries, as every
 * other query does (`QueryProvider`).
 */
export function retryWhileUnreachable(failureCount: number, error: unknown): boolean {
	return isUnreachable(error) || failureCount < 2;
}

/** What stands in for a read's data while there is none. */
export type Waiting = "loading" | "unreachable" | "failed";

/** The part of a TanStack query result `waitingFor` reads. */
export interface QueryState {
	data: unknown;
	isError: boolean;
	isPaused: boolean;
	failureCount: number;
	failureReason: unknown;
}

/**
 * What a page shows in place of a read's data: nothing once there is data (a
 * later refetch that fails leaves the last answer up), "failed" once the read
 * has given up, "unreachable" while it is still trying a server it cannot
 * reach — paused offline, or retrying after a call that got no answer — and
 * "loading" otherwise.
 */
export function waitingFor(query: QueryState): Waiting | null {
	if (query.data !== undefined) return null;
	if (query.isError) return "failed";
	if (query.isPaused) return "unreachable";
	if (query.failureCount > 0 && isUnreachable(query.failureReason)) return "unreachable";
	return "loading";
}
