/**
 * Tests for the URL-parameter mapping in fetchFlowWindows /
 * fetchFlowWindowsSummary. The camelCase TypeScript options translate
 * to snake_case API query params; a refactor that drops a mapping
 * (e.g. forgets `bundleId → bundle_id`) would silently produce a
 * full-table fetch with no filter applied — server happily ignores
 * unknown params, so the bug only surfaces as "this filter doesn't
 * work" with no error to grep for.
 *
 * We mock global fetch and assert on the URL the client built.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchFlowWindows, fetchFlowWindowsSummary } from "./sessionApi";

const fetchMock = vi.fn();

beforeEach(() => {
	vi.stubGlobal("fetch", fetchMock);
	fetchMock.mockResolvedValue({
		ok: true,
		status: 200,
		// Return the minimal shape each endpoint expects so parseApiResponse
		// doesn't blow up on a Zod mismatch.
		json: async () => [],
	} as Response);
});

afterEach(() => {
	fetchMock.mockReset();
	vi.unstubAllGlobals();
});

function lastFetchUrl(): URL {
	const calls = fetchMock.mock.calls;
	if (calls.length === 0) throw new Error("fetch was not called");
	const raw = calls[calls.length - 1][0] as string;
	// fetchFlowWindows builds an absolute URL via config.apiBaseUrl —
	// strip the origin so we can query .searchParams reliably regardless
	// of test environment.
	return new URL(raw, "http://localhost");
}

describe("fetchFlowWindows URL building", () => {
	it("hits /api/signals/flow-windows with start + end", async () => {
		await fetchFlowWindows("2026-04-30T00:00:00Z", "2026-05-01T00:00:00Z");
		const url = lastFetchUrl();
		expect(url.pathname).toBe("/api/signals/flow-windows");
		expect(url.searchParams.get("start")).toBe("2026-04-30T00:00:00Z");
		expect(url.searchParams.get("end")).toBe("2026-05-01T00:00:00Z");
	});

	it("maps camelCase options to snake_case API params", async () => {
		await fetchFlowWindows("2026-04-30T00:00:00Z", "2026-05-01T00:00:00Z", {
			projectId: "p123",
			editorRepo: "/Users/me/code/beats",
			editorLanguage: "go",
			bundleId: "com.microsoft.VSCode",
		});
		const url = lastFetchUrl();
		expect(url.searchParams.get("project_id")).toBe("p123");
		expect(url.searchParams.get("editor_repo")).toBe("/Users/me/code/beats");
		expect(url.searchParams.get("editor_language")).toBe("go");
		expect(url.searchParams.get("bundle_id")).toBe("com.microsoft.VSCode");
	});

	it("omits filter params when their values are empty", async () => {
		await fetchFlowWindows("2026-04-30T00:00:00Z", "2026-05-01T00:00:00Z", {
			projectId: "",
			editorRepo: undefined,
		});
		const url = lastFetchUrl();
		// Server accepts unknown/empty params silently, but the URL
		// reads as a vanilla call — clearer in logs.
		expect(url.searchParams.has("project_id")).toBe(false);
		expect(url.searchParams.has("editor_repo")).toBe(false);
	});

	it("URL-encodes filter values containing special characters", async () => {
		// Repo paths can contain spaces (rare but legal on macOS), and
		// user-supplied repo strings could plausibly contain & or = if
		// the daemon ever surfaces a non-path string. URLSearchParams
		// handles encoding for us; this test locks in that we pass
		// through it rather than building the URL by string concat.
		await fetchFlowWindows("2026-04-30T00:00:00Z", "2026-05-01T00:00:00Z", {
			editorRepo: "/Users/me/My Code/x&y",
		});
		const url = lastFetchUrl();
		expect(url.searchParams.get("editor_repo")).toBe("/Users/me/My Code/x&y");
	});
});

describe("fetchFlowWindowsSummary URL building", () => {
	beforeEach(() => {
		// Different default response — /summary returns an object.
		fetchMock.mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => ({
				count: 0,
				avg: 0,
				peak: 0,
				peak_at: null,
				top_repo: null,
				top_language: null,
				top_bundle: null,
			}),
		} as Response);
	});

	it("hits /api/signals/flow-windows/summary, not the list endpoint", async () => {
		await fetchFlowWindowsSummary("2026-04-30T00:00:00Z", "2026-05-01T00:00:00Z");
		const url = lastFetchUrl();
		expect(url.pathname).toBe("/api/signals/flow-windows/summary");
	});

	it("maps the same filter options as fetchFlowWindows", async () => {
		await fetchFlowWindowsSummary("2026-04-30T00:00:00Z", "2026-05-01T00:00:00Z", {
			projectId: "p123",
			editorRepo: "/Users/me/code/beats",
			editorLanguage: "go",
			bundleId: "com.microsoft.VSCode",
		});
		const url = lastFetchUrl();
		expect(url.searchParams.get("project_id")).toBe("p123");
		expect(url.searchParams.get("editor_repo")).toBe("/Users/me/code/beats");
		expect(url.searchParams.get("editor_language")).toBe("go");
		expect(url.searchParams.get("bundle_id")).toBe("com.microsoft.VSCode");
	});
});
