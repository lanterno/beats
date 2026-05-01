import { describe, expect, it } from "vitest";
import { shortBundleLabel } from "./bundleLabel";

describe("shortBundleLabel", () => {
	it("returns the human-friendly label for known apps", () => {
		expect(shortBundleLabel("com.microsoft.VSCode")).toBe("VS Code");
		expect(shortBundleLabel("com.apple.dt.Xcode")).toBe("Xcode");
		expect(shortBundleLabel("com.jetbrains.goland")).toBe("GoLand");
	});

	it("falls back to the trailing reverse-DNS segment for unknown apps", () => {
		// Cursor isn't in the map; the fallback segment is the
		// pseudo-random todesktop id, which is at least
		// recognizable from logs.
		expect(shortBundleLabel("com.todesktop.230313mzl4w4u92")).toBe("230313mzl4w4u92");
		// Generic unknown app — last segment wins.
		expect(shortBundleLabel("com.example.MyApp")).toBe("MyApp");
	});

	it("returns the input unchanged when there are no dots", () => {
		// Rare but possible — a bundle id without a reverse-DNS prefix
		// shouldn't crash or empty out.
		expect(shortBundleLabel("standalone")).toBe("standalone");
	});

	it("returns empty string for empty input", () => {
		// Defensive: a callers passing top_bundle?.key when top_bundle
		// is null could land here via "" fallback.
		expect(shortBundleLabel("")).toBe("");
	});
});
