import { describe, expect, it } from "vitest";
import { isLoopbackUrl, publicApiBase } from "./index";

describe("publicApiBase", () => {
	it("spells out the same-origin build's empty base as the page's origin", () => {
		expect(publicApiBase("", "http://home.lan:6008")).toBe("http://home.lan:6008");
	});

	it("keeps a configured base, not the SPA's origin, on the split deployment", () => {
		expect(publicApiBase("https://api.lifepete.com", "https://lifepete.com")).toBe(
			"https://api.lifepete.com",
		);
	});
});

describe("isLoopbackUrl", () => {
	it.each([
		"http://localhost:6008",
		"http://app.localhost",
		"http://127.0.0.2:7999",
		"http://[::1]:6008",
	])("%s is this machine", (url) => {
		expect(isLoopbackUrl(url)).toBe(true);
	});

	it.each([
		"http://home.lan:6008",
		"https://api.lifepete.com",
		"http://192.168.1.5:6008",
		"http://localhost.example.com",
	])("%s is reachable from another device", (url) => {
		expect(isLoopbackUrl(url)).toBe(false);
	});
});
