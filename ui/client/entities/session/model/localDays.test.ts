import { describe, expect, it } from "vitest";
import { groupSessionsByLocalDay } from "./localDays";
import type { Session } from "./types";

// Local wall-clock instants, so the test reads the same in every timezone.
function local(y: number, m: number, d: number, h: number, min = 0): string {
	return new Date(y, m - 1, d, h, min).toISOString();
}

function session(id: string, start: string, minutes: number): Session {
	const end = new Date(new Date(start).getTime() + minutes * 60_000).toISOString();
	return { id, projectId: "p", startTime: start, endTime: end, duration: minutes, tags: [] };
}

describe("groupSessionsByLocalDay", () => {
	it("keeps a session that crosses midnight whole on the day it started", () => {
		// Mon Sep 7 2026 23:30 → Tue 01:10: Monday's, in full.
		const days = groupSessionsByLocalDay(
			[session("late", local(2026, 9, 7, 23, 30), 100), session("tue", local(2026, 9, 8, 9), 60)],
			"2026-09-07",
		);
		expect(days.map((d) => d.date)).toEqual([
			"2026-09-07",
			"2026-09-08",
			"2026-09-09",
			"2026-09-10",
			"2026-09-11",
			"2026-09-12",
			"2026-09-13",
		]);
		expect(days[0]).toMatchObject({ totalMinutes: 100, sessionCount: 1 });
		expect(days[0].sessions.map((s) => s.id)).toEqual(["late"]);
		expect(days[1]).toMatchObject({ totalMinutes: 60, sessionCount: 1 });
	});

	it("gives an empty week seven empty days, and leaves other weeks' sessions out", () => {
		const days = groupSessionsByLocalDay(
			[session("prev", local(2026, 9, 6, 10), 30)],
			"2026-09-07",
		);
		expect(days).toHaveLength(7);
		expect(days.every((d) => d.sessionCount === 0 && d.totalMinutes === 0)).toBe(true);
	});

	it("orders a day's sessions by start whatever order they came in", () => {
		const days = groupSessionsByLocalDay(
			[session("pm", local(2026, 9, 9, 14), 30), session("am", local(2026, 9, 9, 8), 30)],
			"2026-09-07",
		);
		expect(days[2].sessions.map((s) => s.id)).toEqual(["am", "pm"]);
	});
});
