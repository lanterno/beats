import { describe, expect, it } from "vitest";
import { fetchStatus, parseStatus, showsBanner, statusSentence } from "./status";

const doc = {
	state: "outage",
	message: "Sign-in is down.",
	affected: ["sign-in"],
	updated_at: "2026-11-14T12:00:00+00:00",
	posts: [
		{
			at: "2026-11-14T12:00:00+00:00",
			state: "outage",
			message: "Sign-in is down.",
			affected: ["sign-in"],
		},
	],
};

describe("parseStatus", () => {
	it("reads a file and refuses what is not one", () => {
		expect(parseStatus(doc)?.state).toBe("outage");
		expect(parseStatus({ state: "on fire", updated_at: "x" })).toBeNull();
		expect(parseStatus("<!doctype html>")).toBeNull();
		expect(parseStatus(null)).toBeNull();
	});

	it("drops a post it cannot read and keeps the rest", () => {
		const parsed = parseStatus({ ...doc, posts: [...doc.posts, { nonsense: true }] });
		expect(parsed?.posts).toHaveLength(1);
	});
});

describe("statusSentence and the banner", () => {
	it("says each state plainly, with what is affected", () => {
		const parsed = parseStatus(doc);
		expect(parsed && statusSentence(parsed)).toBe("Something is down (sign-in).");
		expect(statusSentence({ ...parsed!, state: "operational", affected: [] })).toBe(
			"Everything is working.",
		);
		expect(statusSentence({ ...parsed!, state: "maintenance", affected: [] })).toBe(
			"Planned maintenance is under way.",
		);
	});

	it("shows the banner only when something is not operational, and never on a failed fetch", () => {
		expect(showsBanner(parseStatus(doc))).toBe(true);
		expect(showsBanner(parseStatus({ ...doc, state: "operational" }))).toBe(false);
		expect(showsBanner(null)).toBe(false);
	});
});

describe("fetchStatus", () => {
	it("is null for a failed fetch, a bad status and a body that is not a file", async () => {
		const failing = (() => Promise.reject(new Error("offline"))) as unknown as typeof fetch;
		expect(await fetchStatus("u", failing)).toBeNull();
		const gone = (() =>
			Promise.resolve(new Response("", { status: 404 }))) as unknown as typeof fetch;
		expect(await fetchStatus("u", gone)).toBeNull();
		const html = (() =>
			Promise.resolve(new Response("<!doctype html>", { status: 200 }))) as unknown as typeof fetch;
		expect(await fetchStatus("u", html)).toBeNull();
	});

	it("reads a good file", async () => {
		const ok = (() =>
			Promise.resolve(
				new Response(JSON.stringify(doc), { status: 200 }),
			)) as unknown as typeof fetch;
		expect((await fetchStatus("u", ok))?.state).toBe("outage");
	});
});
