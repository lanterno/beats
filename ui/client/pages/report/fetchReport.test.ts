/**
 * The report page's request: the fragment is read before anything is sent,
 * the body carries the token and nothing carries a credential, even with a
 * session in this browser, and no answer (a 401 included) signs anyone out.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchReport, tokenFromHash } from "./fetchReport";

const TOKEN = `lpr_${"a".repeat(43)}`;

function answering(status: number, body: unknown = {}) {
	return vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => {
		return new Response(JSON.stringify(body), {
			status,
			headers: { "Content-Type": "application/json" },
		});
	});
}

afterEach(() => {
	localStorage.clear();
	vi.restoreAllMocks();
});

describe("tokenFromHash", () => {
	it.each([
		"",
		"#",
		"#x",
		`#lpr_${"a".repeat(42)}`,
		`#lpr_${"a".repeat(44)}`,
		`#lpr_${"a".repeat(42)}+`,
		`#${"a".repeat(47)}`,
	])("declines %j", (hash) => {
		expect(tokenFromHash(hash)).toBeNull();
	});

	it("reads a well-formed token", () => {
		expect(tokenFromHash(`#${TOKEN}`)).toBe(TOKEN);
	});
});

describe("fetchReport", () => {
	it("the request omits credentials and carries no Authorization", async () => {
		localStorage.setItem("beats_session_token", "t");
		const fetchImpl = answering(404);
		await fetchReport(TOKEN, fetchImpl);

		expect(fetchImpl).toHaveBeenCalledTimes(1);
		const [url, init] = fetchImpl.mock.calls[0];
		expect(String(url)).toMatch(/\/api\/public\/reports$/);
		expect(init?.method).toBe("POST");
		expect(init?.credentials).toBe("omit");
		expect(new Headers(init?.headers).has("Authorization")).toBe(false);
		expect(JSON.parse(String(init?.body))).toEqual({ token: TOKEN });
	});

	it("404 is dead, 429 is limited, 500 and a TypeError are unreachable", async () => {
		expect(await fetchReport(TOKEN, answering(404))).toEqual({ kind: "dead" });
		expect(await fetchReport(TOKEN, answering(429))).toEqual({ kind: "limited" });
		expect(await fetchReport(TOKEN, answering(500))).toEqual({ kind: "unreachable" });
		const offline = vi.fn(async () => {
			throw new TypeError("Failed to fetch");
		});
		expect(await fetchReport(TOKEN, offline)).toEqual({ kind: "unreachable" });
	});

	it("a 200 that is not a report is unreachable, never drawn", async () => {
		expect(await fetchReport(TOKEN, answering(200, { detail: "x" }))).toEqual({
			kind: "unreachable",
		});
	});

	it("a 401 never signs anyone out", async () => {
		const replace = vi.fn();
		vi.spyOn(window, "location", "get").mockReturnValue({
			...window.location,
			replace,
		} as Location);
		localStorage.setItem("beats_session_token", "t");

		expect(await fetchReport(TOKEN, answering(401))).toEqual({ kind: "unreachable" });
		expect(replace).not.toHaveBeenCalled();
		expect(localStorage.getItem("beats_session_token")).toBe("t");
	});
});
