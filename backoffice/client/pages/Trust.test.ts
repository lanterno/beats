import { describe, expect, it } from "vitest";
import { waveSentence } from "./Trust";

const wave = (fields: Record<string, unknown>) => ({
	hour: "2026-11-14T09",
	completed: 0,
	usual: 0,
	accounts_with_writes: 0,
	largest_group: null,
	largest_key: null,
	groups: 0,
	...fields,
});

describe("waveSentence", () => {
	it("says when no network is large enough to show, and never names a key", () => {
		const said = waveSentence(wave({ completed: 3, usual: 1.5, groups: 2 }));
		expect(said).toBe(
			"3 accounts were created this hour, usually about 1.5. No network is large enough to show.",
		);
	});

	it("calls the largest network A and counts who wrote anything", () => {
		const said = waveSentence(
			wave({
				completed: 84,
				usual: 14,
				largest_group: 71,
				largest_key: "0123456789abcdef0123456789abcdef",
				accounts_with_writes: 3,
			}),
		);
		expect(said).toBe(
			"84 accounts were created this hour, usually about 14. Network A is 71 of them. Of all 84, 3 have written anything.",
		);
		expect(said).not.toContain("0123456789abcdef");
	});
});
