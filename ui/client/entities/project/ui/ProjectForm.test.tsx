import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/shared/api";
import type { Contract } from "../model";
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
		expect(onSubmit).toHaveBeenCalledWith(
			expect.objectContaining({
				name: "Alpha",
				description: "notes",
				color: "#FBBF24",
				weeklyGoal: "12.5",
				goalType: "cap",
				category: "",
				githubRepo: "",
				autostartRepos: [],
				kind: "side_project",
			}),
		);
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

	it("FF.11: the goal-type radiogroup has a real accessible name (legend id resolves)", () => {
		render(<ProjectForm onSubmit={vi.fn()} />);
		// aria-labelledby="project-form-goal-type" must now resolve to the
		// legend's id, so the group announces "Goal type" — not the
		// unlabeled-group disaster pre-FF.11.
		expect(screen.getByRole("radiogroup", { name: "Goal type" })).toBeInTheDocument();
	});

	it("FF.11: consecutive new projects get different default colors (no more always #5B9CF6)", () => {
		// Render two ProjectForms back-to-back. Their default color seeds
		// differ — pre-FF.11 both came out #5B9CF6 because assignColor("new")
		// always hashed to PROJECT_COLORS[0].
		const { unmount } = render(<ProjectForm onSubmit={vi.fn()} />);
		const firstHex = screen.getByText(/#[0-9A-F]{6}/).textContent;
		unmount();

		render(<ProjectForm onSubmit={vi.fn()} />);
		const secondHex = screen.getByText(/#[0-9A-F]{6}/).textContent;
		expect(secondHex).not.toBe(firstHex);
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

	describe("work contracts", () => {
		const CONTRACT: Contract = {
			terms: [
				{
					effectiveFrom: "2026-01-05",
					scheduleType: "part_time",
					fullTimeHours: 42,
					percentage: 0.8,
				},
			],
			openingBalanceHours: 0,
		};

		it("hides the personal goal on a time-based day job and shows it on an objective one", async () => {
			render(<ProjectForm onSubmit={vi.fn()} />);
			expect(screen.getByLabelText(/Weekly goal/)).toBeInTheDocument();

			await userEvent.click(screen.getByRole("radio", { name: /Day job/ }));
			// Full time is the default schedule: the contract is the goal.
			expect(screen.queryByLabelText(/Weekly goal/)).not.toBeInTheDocument();
			expect(screen.queryByRole("radiogroup", { name: "Goal type" })).not.toBeInTheDocument();
			expect(screen.getByRole("radiogroup", { name: "Schedule" })).toBeInTheDocument();

			await userEvent.click(screen.getByRole("radio", { name: /Objective/ }));
			expect(screen.getByLabelText(/Personal weekly goal/)).toBeInTheDocument();
			expect(screen.getByRole("radiogroup", { name: "Goal type" })).toBeInTheDocument();

			// And back on a side project the ordinary goal returns.
			await userEvent.click(screen.getByRole("radio", { name: /Side project/ }));
			expect(screen.getByLabelText(/Weekly goal/)).toBeInTheDocument();
			expect(screen.queryByRole("radiogroup", { name: "Schedule" })).not.toBeInTheDocument();
		});

		it("asks for the numbers each schedule type needs", async () => {
			render(<ProjectForm onSubmit={vi.fn()} initialValues={{ kind: "day_job" }} />);
			// Full time: a basis, no percentage.
			expect(screen.getByLabelText(/Full-time week/)).toBeInTheDocument();
			expect(screen.queryByLabelText("Percentage")).not.toBeInTheDocument();

			await userEvent.click(screen.getByRole("radio", { name: /Part time/ }));
			expect(screen.getByLabelText(/Full-time week/)).toBeInTheDocument();
			expect(screen.getByLabelText("Percentage")).toBeInTheDocument();

			await userEvent.click(screen.getByRole("radio", { name: /Custom/ }));
			expect(screen.getByLabelText("Hours per week")).toBeInTheDocument();
			expect(screen.queryByLabelText("Percentage")).not.toBeInTheDocument();
			expect(screen.queryByLabelText(/Full-time week/)).not.toBeInTheDocument();

			await userEvent.click(screen.getByRole("radio", { name: /Objective/ }));
			expect(screen.queryByLabelText("Hours per week")).not.toBeInTheDocument();
			expect(screen.queryByLabelText(/Full-time week/)).not.toBeInTheDocument();
		});

		it("submits a new day job's first term and refuses one without its numbers", async () => {
			const onSubmit = vi.fn();
			render(<ProjectForm onSubmit={onSubmit} initialValues={{ name: "Employer" }} />);
			await userEvent.click(screen.getByRole("radio", { name: /Day job/ }));
			await userEvent.click(screen.getByRole("radio", { name: /Part time/ }));

			// Nothing typed yet: the API would 422, so the form stops here.
			await userEvent.click(screen.getByRole("button", { name: "Save" }));
			expect(onSubmit).not.toHaveBeenCalled();
			expect(screen.getByLabelText(/Full-time week/)).toHaveAttribute("aria-invalid", "true");
			expect(screen.getByLabelText("Percentage")).toHaveAttribute("aria-invalid", "true");

			await userEvent.type(screen.getByLabelText(/Full-time week/), "42");
			await userEvent.type(screen.getByLabelText("Percentage"), "80");
			await userEvent.click(screen.getByRole("button", { name: "Save" }));

			expect(onSubmit).toHaveBeenCalledWith(
				expect.objectContaining({
					kind: "day_job",
					term: expect.objectContaining({
						scheduleType: "part_time",
						fullTimeHours: "42",
						percentage: "80",
					}),
				}),
			);
		});

		it("moves focus to the first input at fault when a submit is refused", async () => {
			render(
				<ProjectForm onSubmit={vi.fn()} initialValues={{ name: "Employer", kind: "day_job" }} />,
			);
			await userEvent.click(screen.getByRole("button", { name: "Save" }));
			expect(document.activeElement).toBe(screen.getByLabelText(/Full-time week/));
		});

		it("shows an existing contract's current term read-only, with the way to the history", async () => {
			const onChangeContract = vi.fn();
			render(
				<ProjectForm
					onSubmit={vi.fn()}
					initialValues={{ name: "Employer", kind: "day_job" }}
					existingContract={CONTRACT}
					onChangeContract={onChangeContract}
				/>,
			);
			expect(screen.getByText(/Part time · 80% of 42 h · 33.6 h\/week/)).toBeInTheDocument();
			expect(screen.queryByRole("radiogroup", { name: "Schedule" })).not.toBeInTheDocument();
			// Time-based today, so no personal goal; the frame stays editable.
			expect(screen.queryByLabelText(/Weekly goal/)).not.toBeInTheDocument();
			expect(screen.getByLabelText("Holiday region")).toBeInTheDocument();
			expect(screen.getByLabelText(/Ended on/)).toBeInTheDocument();

			await userEvent.click(screen.getByRole("button", { name: /Change contract/ }));
			expect(onChangeContract).toHaveBeenCalledTimes(1);
		});

		it("pins a 422's fields to the inputs they name", () => {
			render(
				<ProjectForm
					onSubmit={vi.fn()}
					initialValues={{ name: "Employer", kind: "day_job" }}
					submitError={
						new ApiError(422, "Validation failed", "VALIDATION_ERROR", [
							{ path: "name", message: "too long", type: "string_too_long" },
							{
								path: "contract.terms.0.full_time_hours",
								message: "must be positive",
								type: "value_error",
							},
							{ path: "contract.terms", message: "terms must be in order", type: "value_error" },
						])
					}
				/>,
			);
			expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
			expect(screen.getByText("too long")).toBeInTheDocument();
			expect(screen.getByLabelText(/Full-time week/)).toHaveAttribute("aria-invalid", "true");
			expect(screen.getByText("must be positive")).toBeInTheDocument();
			// No input for the terms as a whole: it reads as a general message.
			expect(screen.getByRole("alert")).toHaveTextContent("terms must be in order");
		});
	});
});
