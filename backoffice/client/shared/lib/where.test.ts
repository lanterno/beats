import { describe, expect, it } from "vitest";
import { deployment } from "./where";

describe("deployment", () => {
	it("names production by its hostname", () => {
		expect(deployment("backoffice.lifepete.com")).toEqual({ label: "Production", live: true });
	});

	it("reads the run.app URL as production too, because its data is", () => {
		// IAP fronts both. Writes from it are refused on Origin, but what is
		// read there is real people's, so the label must not say otherwise.
		const where = deployment("beats-operator-abc123-ew.a.run.app");
		expect(where.live).toBe(true);
		expect(where.label).toContain("Production");
	});

	it("is local anywhere else", () => {
		expect(deployment("localhost")).toEqual({ label: "Local", live: false });
		expect(deployment("127.0.0.1").live).toBe(false);
	});

	// A hostname arrives from the browser lowercased, but it is compared
	// rather than displayed, and the comparison decides whether the page
	// says "Production". Getting it wrong in the safe direction is still wrong.
	it("matches whatever the case", () => {
		expect(deployment("BACKOFFICE.LIFEPETE.COM").live).toBe(true);
	});

	// The nearest wrong answer: a hostname that merely ends in the real one.
	it("is not fooled by a lookalike host", () => {
		expect(deployment("notbackoffice.lifepete.com").live).toBe(false);
		expect(deployment("backoffice.lifepete.com.evil.test").live).toBe(false);
		expect(deployment("run.app.evil.test").live).toBe(false);
	});
});
