import { describe, expect, it } from "vitest";
import { intentOf, PAGES, pagesFor, reviewsFor } from "./palette";

const ID = "65a1f0c2b3d4e5f601234567";

describe("intentOf", () => {
	it("knows a whole id and a whole address", () => {
		expect(intentOf(` ${ID} `)).toEqual({ kind: "id", id: ID });
		expect(intentOf("maya@example.com")).toEqual({ kind: "address", address: "maya@example.com" });
	});

	// The palette must not become a way to browse people.
	it("refuses a fragment of an address or an id", () => {
		for (const fragment of ["maya@", "maya@example", "@example.com", ID.slice(0, 12), "maya"]) {
			expect(intentOf(fragment).kind).toBe("fragment");
		}
	});
});

describe("what a fragment reaches", () => {
	it("filters pages and never offers an account or a command", () => {
		const intent = intentOf("aud");
		expect(pagesFor(intent).map((p) => p.label)).toEqual(["Audit log"]);
		expect(reviewsFor(intent)).toEqual([]);
	});

	it("lists every page for nothing typed", () => {
		expect(pagesFor(intentOf(""))).toHaveLength(PAGES.length);
	});
});

describe("what an id reaches", () => {
	it("opens the account and each command's review, never the act itself", () => {
		const to = reviewsFor(intentOf(ID)).map((d) => d.to);
		expect(to[0]).toBe(`/accounts/${ID}`);
		expect(to.slice(1).every((path) => path.startsWith("/review/") && path.endsWith(ID))).toBe(
			true,
		);
	});
});

describe("what an address reaches", () => {
	// It is looked up through a POST; no destination carries it into a URL.
	it("is in no destination", () => {
		const intent = intentOf("maya@example.com");
		expect([...pagesFor(intent), ...reviewsFor(intent)]).toEqual([]);
	});
});
