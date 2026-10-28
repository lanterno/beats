/**
 * The owner's closing section (#347). What is pinned is the one rule the
 * component computes itself: deletion stays locked until the closing day —
 * the API refuses it anyway, but the button must say why before a click
 * has to explain. The notice floor and the hand-back live in the API's
 * tests.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Organisation } from "@/entities/organisation";
import { ClosingSection } from "./ClosingSection";

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	const idle = () => ({ isPending: false, mutate: vi.fn() });
	return {
		...actual,
		useBeginClosing: idle,
		useCancelClosing: idle,
		useDeleteOrganisation: idle,
	};
});

function org(closesOn?: string): Organisation {
	return {
		id: "o1",
		name: "Acme",
		weekStart: "monday",
		timezone: "UTC",
		createdAt: "2026-01-01T00:00:00Z",
		closesOn,
	};
}

function renderSection(closesOn?: string) {
	render(
		<MemoryRouter>
			<ClosingSection organisation={org(closesOn)} />
		</MemoryRouter>,
	);
}

afterEach(cleanup);

describe("ClosingSection", () => {
	it("offers to start the notice while nothing is closing", () => {
		renderSection();
		expect(screen.getByText("Close Acme…")).toBeTruthy();
		expect(screen.queryByText(/Delete now|Unlocks/)).toBeNull();
	});

	it("keeps deletion locked until the closing day, and says when", () => {
		renderSection("2199-01-01");
		const locked = screen.getByRole("button", { name: "Unlocks 2199-01-01" });
		expect(locked.hasAttribute("disabled")).toBe(true);
	});

	it("unlocks deletion once the day has come", () => {
		renderSection("2020-01-01");
		const unlocked = screen.getByRole("button", { name: "Delete now" });
		expect(unlocked.hasAttribute("disabled")).toBe(false);
	});
});
