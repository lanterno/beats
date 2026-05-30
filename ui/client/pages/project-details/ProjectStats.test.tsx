import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Session } from "@/entities/session";
import { ProjectStats } from "./ProjectStats";

function session(overrides: Partial<Session>): Session {
	return {
		id: "x",
		projectId: "p1",
		startTime: "2026-05-30T10:00:00Z",
		endTime: "2026-05-30T10:30:00Z",
		duration: 30,
		note: "",
		tags: [],
		...overrides,
	} as Session;
}

describe("ProjectStats", () => {
	afterEach(cleanup);

	it("renders all four cards when there are completed sessions", () => {
		render(
			<ProjectStats
				sessions={[
					session({ id: "a", duration: 30, startTime: "2026-05-29T10:00:00Z" }),
					session({ id: "b", duration: 90, startTime: "2026-05-30T10:00:00Z" }),
				]}
				lastTrackedAt="2026-05-30T10:30:00Z"
			/>,
		);
		expect(screen.getByText("Avg session")).toBeInTheDocument();
		expect(screen.getByText("Longest")).toBeInTheDocument();
		expect(screen.getByText("Sessions")).toBeInTheDocument();
		expect(screen.getByText("Last tracked")).toBeInTheDocument();
		expect(screen.getByText("2")).toBeInTheDocument();
	});

	it("renders just the last-tracked card when there are no completed sessions", () => {
		render(<ProjectStats sessions={[]} lastTrackedAt={undefined} />);
		expect(screen.getByText("Last tracked")).toBeInTheDocument();
		// The other three labels stay off the page.
		expect(screen.queryByText("Avg session")).not.toBeInTheDocument();
	});

	it("falls back to the most-recent session's time when lastTrackedAt is absent", () => {
		render(
			<ProjectStats sessions={[session({ duration: 30, endTime: "2026-05-30T10:30:00Z" })]} />,
		);
		// Any formatted relative-time value is fine; just confirm the card
		// isn't rendering the empty-state em-dash.
		expect(screen.queryByText("Last tracked")?.nextElementSibling?.textContent).not.toBe("—");
	});
});
