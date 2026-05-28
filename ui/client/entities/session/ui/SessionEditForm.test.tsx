/**
 * Tests for SessionEditForm — the inline session editor.
 *
 * Pins the start-before-end guard: a session whose end is at or before its
 * start must not be savable, and the Save button is disabled with an inline
 * message. A valid range stays savable and forwards the edited values.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectOption, Session } from "../model";
import { SessionEditForm } from "./SessionEditForm";

const projects: ProjectOption[] = [
	{ id: "p1", name: "Project One" },
	{ id: "p2", name: "Project Two" },
];

function makeSession(overrides: Partial<Session> = {}): Session {
	return {
		id: "s1",
		projectId: "p1",
		startTime: "2026-04-07T10:00:00Z",
		endTime: "2026-04-07T11:00:00Z",
		duration: 60,
		tags: [],
		...overrides,
	};
}

function renderForm(session: Session) {
	const onSave = vi.fn();
	const onCancel = vi.fn();
	render(
		<SessionEditForm session={session} projects={projects} onSave={onSave} onCancel={onCancel} />,
	);
	return { onSave, onCancel };
}

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe("SessionEditForm start/end validation", () => {
	it("allows saving a valid range and forwards the values", async () => {
		const { onSave } = renderForm(makeSession());
		const saveBtn = screen.getByRole("button", { name: /Save/i });
		expect(saveBtn).not.toBeDisabled();

		await userEvent.click(saveBtn);
		expect(onSave).toHaveBeenCalledWith("s1", "2026-04-07T10:00:00Z", "2026-04-07T11:00:00Z", "p1");
	});

	it("blocks saving when end equals start", () => {
		const { onSave } = renderForm(makeSession({ endTime: "2026-04-07T10:00:00Z" }));
		const saveBtn = screen.getByRole("button", { name: /Save/i });
		expect(saveBtn).toBeDisabled();
		expect(screen.getByRole("alert")).toHaveTextContent(/end time must be after the start time/i);
		fireEvent.click(saveBtn);
		expect(onSave).not.toHaveBeenCalled();
	});

	it("blocks saving when end is before start, and re-enables once the range becomes valid", async () => {
		const { onSave } = renderForm(
			makeSession({ startTime: "2026-04-07T12:00:00Z", endTime: "2026-04-07T10:00:00Z" }),
		);
		const saveBtn = screen.getByRole("button", { name: /Save/i });
		expect(saveBtn).toBeDisabled();
		expect(screen.getByRole("alert")).toBeInTheDocument();

		// Move the End input far ahead of Start; the guard should clear.
		// Two datetime-local inputs render in order: [Start, End].
		const dtInputs = document.querySelectorAll<HTMLInputElement>('input[type="datetime-local"]');
		expect(dtInputs.length).toBe(2);
		fireEvent.change(dtInputs[1], { target: { value: "2026-04-08T13:00" } });

		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
		expect(saveBtn).not.toBeDisabled();
		await userEvent.click(saveBtn);
		expect(onSave).toHaveBeenCalledTimes(1);
	});
});
