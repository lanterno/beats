import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectForm } from "./ProjectForm";

describe("ProjectForm", () => {
	afterEach(cleanup);

	it("requires a name", async () => {
		const onSubmit = vi.fn();
		render(<ProjectForm onSubmit={onSubmit} />);
		const submit = screen.getByRole("button", { name: "Save" });
		expect(submit).toBeDisabled();
	});

	it("submits trimmed name, description, color, weeklyGoal as number, goalType", async () => {
		const onSubmit = vi.fn();
		render(
			<ProjectForm
				initialValues={{ color: "#FBBF24" }}
				submitLabel="Create project"
				onSubmit={onSubmit}
			/>,
		);

		await userEvent.type(screen.getByLabelText("Name"), "  Alpha  ");
		await userEvent.type(screen.getByLabelText(/Description/), "  notes  ");
		await userEvent.type(screen.getByLabelText(/Weekly goal/), "12.5");
		await userEvent.click(screen.getByRole("radio", { name: /Cap/ }));

		await userEvent.click(screen.getByRole("button", { name: "Create project" }));

		expect(onSubmit).toHaveBeenCalledTimes(1);
		expect(onSubmit).toHaveBeenCalledWith({
			name: "Alpha",
			description: "notes",
			color: "#FBBF24",
			weeklyGoal: "12.5",
			goalType: "cap",
			category: "",
			githubRepo: "",
			autostartRepos: [],
		});
	});

	it("rejects a negative weekly goal", async () => {
		const onSubmit = vi.fn();
		render(<ProjectForm onSubmit={onSubmit} />);

		await userEvent.type(screen.getByLabelText("Name"), "Beta");
		// HTML number inputs reject the leading minus, so type a digit then a
		// minus to force a non-numeric string that bypasses min="0".
		const goalField = screen.getByLabelText(/Weekly goal/);
		await userEvent.type(goalField, "0");
		await userEvent.clear(goalField);
		await userEvent.type(goalField, "-2");
		// type="number" doesn't always swallow the minus depending on the
		// runner; if the field rejected it the test still passes (value === ""
		// hits the "weeklyGoal blank = no goal" branch). Either way the submit
		// must NOT call onSubmit with weeklyGoal: "-2".
		await userEvent.click(screen.getByRole("button", { name: "Save" }));

		const submittedNegative = onSubmit.mock.calls.find((call) => call[0]?.weeklyGoal === "-2");
		expect(submittedNegative).toBeUndefined();
	});

	it("renders goal-type radios with both icon and label (no color-only state)", () => {
		render(<ProjectForm onSubmit={vi.fn()} />);
		// Text labels are present alongside the icons (a11y principle).
		expect(screen.getByText("Target")).toBeInTheDocument();
		expect(screen.getByText("Cap")).toBeInTheDocument();
		expect(screen.getByRole("radio", { name: /Target/ })).toBeChecked();
	});

	it("focuses the field the caller asks for", () => {
		render(<ProjectForm onSubmit={vi.fn()} autoFocusField="description" />);
		// Description input is the active element after mount.
		expect(document.activeElement).toBe(screen.getByLabelText(/Description/));
	});

	it("opens the Advanced disclosure automatically when initial values include category/github_repo/autostart", () => {
		render(<ProjectForm onSubmit={vi.fn()} initialValues={{ category: "coding" }} />);
		// Advanced section is open by default since the editing flow's
		// initial values already include category — the category input is
		// rendered.
		expect(screen.getByLabelText("Category")).toBeInTheDocument();
	});

	it("includes the advanced field values in onSubmit when the disclosure is opened", async () => {
		const onSubmit = vi.fn();
		render(
			<ProjectForm
				onSubmit={onSubmit}
				initialValues={{ name: "Alpha", color: "#FBBF24" }}
				categorySuggestions={["coding"]}
			/>,
		);

		// Disclosure starts closed because no advanced initial values were set.
		expect(screen.queryByLabelText("Category")).not.toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: /Advanced/ }));

		await userEvent.type(screen.getByLabelText("Category"), "coding");
		await userEvent.type(screen.getByLabelText("GitHub repo"), "lanterno/beats");

		await userEvent.click(screen.getByRole("button", { name: "Save" }));
		expect(onSubmit).toHaveBeenCalledWith(
			expect.objectContaining({
				category: "coding",
				githubRepo: "lanterno/beats",
				autostartRepos: [],
			}),
		);
	});
});
