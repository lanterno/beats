/**
 * Whether the server can be reached, read off a query's retry state.
 *
 * The bug these pin: with the API down, the dashboard said "Loading your
 * projects..." for as long as the outage lasted, because its read gave up, the
 * panels it then drew asked again, and the spinner came back. The pure halves
 * are tested by their inputs; the last block runs them inside a real
 * QueryClient, since `waitingFor` reads TanStack's own retry state and is only
 * right while TanStack keeps that state the way it is read here.
 */
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { isUnreachable, type QueryState, retryWhileUnreachable, waitingFor } from "./reach";

const offline = new TypeError("Failed to fetch");

describe("isUnreachable", () => {
	it("counts a network failure, which fetch throws as a TypeError", () => {
		expect(isUnreachable(offline)).toBe(true);
	});

	it("counts a gateway answering for the API, without the API's envelope", () => {
		for (const status of [502, 503, 504]) {
			expect(isUnreachable(new ApiError(status, "Bad Gateway"))).toBe(true);
		}
	});

	it("does not count an answer the API gave itself, a 503 included", () => {
		expect(isUnreachable(new ApiError(503, "Coach is off", "COACH_NOT_CONFIGURED"))).toBe(false);
		expect(isUnreachable(new ApiError(500, "Boom", "INTERNAL_ERROR"))).toBe(false);
		expect(isUnreachable(new ApiError(500, "Request failed"))).toBe(false);
		expect(isUnreachable(new ApiError(404, "Not found", "NOT_FOUND"))).toBe(false);
	});

	it("does not count other errors, or none", () => {
		expect(isUnreachable(new Error("Failed to fetch"))).toBe(false);
		expect(isUnreachable(null)).toBe(false);
		expect(isUnreachable(undefined)).toBe(false);
	});
});

describe("retryWhileUnreachable", () => {
	it("keeps trying a server it cannot reach, however many tries have failed", () => {
		expect(retryWhileUnreachable(0, offline)).toBe(true);
		expect(retryWhileUnreachable(2, offline)).toBe(true);
		expect(retryWhileUnreachable(500, new ApiError(502, "Bad Gateway"))).toBe(true);
	});

	it("gives up on anything else after two retries, as every other read does", () => {
		const refused = new ApiError(500, "Boom", "INTERNAL_ERROR");
		expect(retryWhileUnreachable(0, refused)).toBe(true);
		expect(retryWhileUnreachable(1, refused)).toBe(true);
		expect(retryWhileUnreachable(2, refused)).toBe(false);
	});
});

describe("waitingFor", () => {
	const fresh: QueryState = {
		data: undefined,
		isError: false,
		isPaused: false,
		failureCount: 0,
		failureReason: null,
	};

	it("is loading before anything has failed", () => {
		expect(waitingFor(fresh)).toBe("loading");
	});

	it("is unreachable while it retries a call that got no answer", () => {
		expect(waitingFor({ ...fresh, failureCount: 1, failureReason: offline })).toBe("unreachable");
	});

	it("is unreachable while the browser is offline and the read is paused", () => {
		expect(waitingFor({ ...fresh, isPaused: true })).toBe("unreachable");
	});

	it("is still loading while it retries a refusal, and failed once it gives up", () => {
		const refused = new ApiError(500, "Boom", "INTERNAL_ERROR");
		expect(waitingFor({ ...fresh, failureCount: 1, failureReason: refused })).toBe("loading");
		expect(waitingFor({ ...fresh, isError: true, failureCount: 3, failureReason: refused })).toBe(
			"failed",
		);
	});

	it("stands in for nothing once there is data, even when a later refetch fails", () => {
		expect(waitingFor({ ...fresh, data: [] })).toBeNull();
		expect(
			waitingFor({ ...fresh, data: [], isError: true, failureCount: 3, failureReason: offline }),
		).toBeNull();
	});
});

describe("inside a QueryClient", () => {
	/** Each state the observer reports, read through `waitingFor`, until it has data or gives up. */
	async function watch(failures: unknown[]): Promise<{ calls: number; seen: unknown[] }> {
		const client = new QueryClient();
		let calls = 0;
		const observer = new QueryObserver(client, {
			queryKey: ["reach"],
			queryFn: async () => {
				const failure = failures[calls++];
				if (failure !== undefined) throw failure;
				return ["a project"];
			},
			retry: retryWhileUnreachable,
			retryDelay: 1,
		});
		const seen: unknown[] = [];
		const stop = observer.subscribe((result) => seen.push(waitingFor(result)));
		await vi.waitFor(() => {
			const now = observer.getCurrentResult();
			expect(now.data !== undefined || now.isError).toBe(true);
		});
		stop();
		client.clear();
		return { calls, seen };
	}

	it("retries an unreachable server past two retries, reading unreachable until it answers", async () => {
		const { calls, seen } = await watch([offline, offline, offline, offline]);
		expect(calls).toBe(5);
		expect(seen).toContain("unreachable");
		expect(seen).not.toContain("failed");
		expect(seen[seen.length - 1]).toBeNull();
	});

	it("gives up on a refusal after two retries, reading failed and never unreachable", async () => {
		const refused = new ApiError(500, "Boom", "INTERNAL_ERROR");
		const { calls, seen } = await watch([refused, refused, refused, refused]);
		expect(calls).toBe(3);
		expect(seen).not.toContain("unreachable");
		expect(seen[seen.length - 1]).toBe("failed");
	});
});
