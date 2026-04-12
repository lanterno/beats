import { describe, expect, it } from "vitest";
import { cn } from "./cn";

describe("cn", () => {
	it("merges class names", () => {
		expect(cn("px-2", "py-1")).toBe("px-2 py-1");
	});

	it("handles conditional classes", () => {
		expect(cn("base", false && "hidden", "visible")).toBe("base visible");
	});

	it("resolves tailwind conflicts (last wins)", () => {
		const result = cn("px-2", "px-4");
		expect(result).toBe("px-4");
	});

	it("handles undefined and null", () => {
		expect(cn("base", undefined, null, "extra")).toBe("base extra");
	});

	it("handles empty call", () => {
		expect(cn()).toBe("");
	});
});
