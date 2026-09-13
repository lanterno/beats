/**
 * Focus returns to what opened the dialog. Radix returns it only to a
 * Trigger, which no dialog here renders, so every close left it on <body>;
 * and when a save takes the opener away, the caller's stand-in takes it.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { Dialog } from "./dialog";

function Page() {
	const [open, setOpen] = useState(false);
	const [booked, setBooked] = useState(false);
	return (
		<>
			{booked ? (
				<button type="button" id="change">
					Change
				</button>
			) : (
				<button type="button" onClick={() => setOpen(true)}>
					Book time off
				</button>
			)}
			<Dialog
				open={open}
				onClose={() => setOpen(false)}
				title="Book time off"
				returnFocus={() => document.getElementById("change")}
			>
				<button
					type="button"
					onClick={() => {
						setBooked(true);
						setOpen(false);
					}}
				>
					Save
				</button>
			</Dialog>
		</>
	);
}

afterEach(cleanup);

describe("Dialog", () => {
	it("gives focus back to the control that opened it", async () => {
		render(<Page />);
		const opener = screen.getByRole("button", { name: "Book time off" });

		await userEvent.click(opener);
		expect(screen.getByRole("dialog")).toBeInTheDocument();
		await userEvent.keyboard("{Escape}");

		await waitFor(() => expect(opener).toHaveFocus());
	});

	it("gives it to the stand-in when a save took the opener away", async () => {
		render(<Page />);

		await userEvent.click(screen.getByRole("button", { name: "Book time off" }));
		await userEvent.click(screen.getByRole("button", { name: "Save" }));

		await waitFor(() => expect(screen.getByRole("button", { name: "Change" })).toHaveFocus());
	});
});
