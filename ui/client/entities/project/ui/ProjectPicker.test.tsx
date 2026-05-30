import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectWithDuration } from "@/entities/project";
import { readPickerRecents } from "../model/pickerRecents";
import { ProjectPicker } from "./ProjectPicker";

vi.mock("@/features/auth", () => ({
	useAuth: () => ({
		user: { email: "alice@example.com" },
		isAuthenticated: true,
		isLoading: false,
		token: "stub",
	}),
}));

function project(overrides: Partial<ProjectWithDuration>): ProjectWithDuration {
	return {
		id: "x",
		name: "x",
		color: "#fff",
		archived: false,
		goalOverrides: [],
		autostartRepos: [],
		totalMinutes: 0,
		weeklyMinutes: 0,
		...overrides,
	} as ProjectWithDuration;
}

const PROJECTS: ProjectWithDuration[] = [
	project({ id: "a", name: "Alpha", description: "first" }),
	project({ id: "b", name: "Beta", description: "second" }),
	project({ id: "g", name: "Gamma" }),
	project({ id: "old", name: "OldProject", archived: true }),
];

describe("ProjectPicker", () => {
	beforeEach(() => {
		window.localStorage.clear();
	});
	afterEach(cleanup);

	it("renders the current selection (color dot + name) and opens the listbox on click", async () => {
		render(<ProjectPicker value="a" onChange={vi.fn()} projects={PROJECTS} />);
		expect(screen.getByRole("button", { name: "Project" })).toHaveTextContent("Alpha");

		await userEvent.click(screen.getByRole("button", { name: "Project" }));

		expect(screen.getByRole("combobox")).toBeInTheDocument();
		expect(screen.getByRole("listbox")).toBeInTheDocument();
		// The archived project is hidden by default — the visibility filter
		// from P0.3 still applies inside the picker.
		expect(screen.queryByRole("option", { name: /OldProject/ })).not.toBeInTheDocument();
	});

	it("filters as the user types", async () => {
		render(<ProjectPicker value={null} onChange={vi.fn()} projects={PROJECTS} />);
		await userEvent.click(screen.getByRole("button", { name: "Project" }));
		const input = screen.getByRole("combobox");
		await userEvent.type(input, "bet");
		// Only Beta is left; Alpha + Gamma are gone.
		expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Beta"]);
	});

	it("ArrowDown / ArrowUp move highlight (aria-activedescendant); Enter selects + closes", async () => {
		const onChange = vi.fn();
		render(<ProjectPicker value={null} onChange={onChange} projects={PROJECTS} />);
		await userEvent.click(screen.getByRole("button", { name: "Project" }));
		const input = screen.getByRole("combobox");

		// First option ("Alpha") is highlighted on open.
		const firstOptionId = screen.getAllByRole("option")[0].id;
		expect(input).toHaveAttribute("aria-activedescendant", firstOptionId);

		// ArrowDown → Beta.
		fireEvent.keyDown(input, { key: "ArrowDown" });
		const secondOptionId = screen.getAllByRole("option")[1].id;
		expect(input).toHaveAttribute("aria-activedescendant", secondOptionId);

		// Enter selects Beta and closes.
		fireEvent.keyDown(input, { key: "Enter" });
		expect(onChange).toHaveBeenCalledWith("b");
		expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
	});

	it("Escape closes without selecting", async () => {
		const onChange = vi.fn();
		render(<ProjectPicker value={null} onChange={onChange} projects={PROJECTS} />);
		await userEvent.click(screen.getByRole("button", { name: "Project" }));

		fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
		expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
		expect(onChange).not.toHaveBeenCalled();
	});

	it("records the selection to user-scoped recents", async () => {
		const onChange = vi.fn();
		render(<ProjectPicker value={null} onChange={onChange} projects={PROJECTS} />);

		await userEvent.click(screen.getByRole("button", { name: "Project" }));
		await userEvent.click(screen.getByRole("option", { name: /Beta/ }));

		expect(onChange).toHaveBeenCalledWith("b");
		expect(readPickerRecents("alice@example.com")).toEqual(["b"]);
	});

	it("surfaces archived rows when showArchived=true", async () => {
		render(<ProjectPicker value={null} onChange={vi.fn()} projects={PROJECTS} showArchived />);
		await userEvent.click(screen.getByRole("button", { name: "Project" }));
		const row = screen.getByRole("option", { name: /OldProject/ });
		expect(row).toBeInTheDocument();
		// The Archived chip is rendered inline so an SR user knows the row's state.
		expect(row).toHaveTextContent("Archived");
	});
});
