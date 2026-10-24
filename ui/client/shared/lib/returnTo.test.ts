import { describe, expect, it } from "vitest";
import { rememberReturnTo, takeReturnTo } from "./returnTo";

function memory() {
	const map = new Map<string, string>();
	return {
		getItem: (k: string) => map.get(k) ?? null,
		setItem: (k: string, v: string) => void map.set(k, v),
		removeItem: (k: string) => void map.delete(k),
	};
}

describe("returnTo", () => {
	it("keeps a local path with its search, once", () => {
		const s = memory();
		rememberReturnTo("/organisations/join/abc?x=1", s);
		expect(takeReturnTo(s)).toBe("/organisations/join/abc?x=1");
		expect(takeReturnTo(s)).toBeNull();
	});

	it("keeps nothing for the homepage or the dashboard", () => {
		const s = memory();
		rememberReturnTo("/", s);
		rememberReturnTo("/app", s);
		expect(takeReturnTo(s)).toBeNull();
	});

	it("never returns to another site", () => {
		const s = memory();
		rememberReturnTo("https://evil.example/", s);
		rememberReturnTo("//evil.example/", s);
		expect(takeReturnTo(s)).toBeNull();
		s.setItem("beats_return_to", "//evil.example/");
		expect(takeReturnTo(s)).toBeNull();
	});
});
