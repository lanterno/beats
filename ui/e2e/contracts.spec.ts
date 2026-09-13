import { expect, type Locator, type Page, test } from "@playwright/test";

/**
 * A day job against its contract, end to end: create one through the form,
 * read the standing, book the coming Friday off through Time off and watch
 * the week's expectation drop by one day's hours, take the day back through
 * the booking dialog, change the contract from a later date and see the
 * register call it planned, then archive the project through the settings
 * drawer.
 *
 * Every run creates its own project — the name carries the clock — and
 * archives it at the end, so what an earlier run left in the database never
 * decides what this one sees.
 */

const FULL_TIME_HOURS = 40;
const PERCENT = 80;
const HOURS_PER_DAY = (FULL_TIME_HOURS * PERCENT) / 100 / 5; // 6.4

/** A local calendar date as the API and the form spell it. */
function isoDate(d: Date): string {
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, "0");
	const day = String(d.getDate()).padStart(2, "0");
	return `${y}-${m}-${day}`;
}

function addDays(d: Date, days: number): Date {
	const next = new Date(d);
	next.setDate(d.getDate() + days);
	return next;
}

/** This week's Monday, at noon local time. */
function thisMonday(): Date {
	const today = new Date();
	today.setHours(12, 0, 0, 0);
	return addDays(today, -((today.getDay() + 6) % 7));
}

/** "Sep 14, 2026" — a term's date as the register lists it. */
function plainDate(d: Date): string {
	return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}, ${d.getFullYear()}`;
}

/** "25.6 h" → 25.6 */
function hoursIn(text: string): number {
	const match = /(-?\d+(?:\.\d+)?)\s*h/.exec(text);
	if (!match) throw new Error(`no hours in "${text}"`);
	return Number(match[1]);
}

function expectedFigure(page: Page): Locator {
	return page
		.getByRole("region", { name: "Where you stand" })
		.getByText("Expected", { exact: true })
		.locator("..")
		.getByRole("definition");
}

test.describe("Work contracts", () => {
	test("a day job's week follows the contract, time off lowers it, and the register plans a change", async ({
		page,
	}) => {
		const name = `Day job ${Date.now()}`;
		const monday = thisMonday();

		await page.goto("/app");
		await page.getByRole("button", { name: "New project" }).first().click();
		const form = page.getByRole("dialog", { name: "New project" });
		await form.getByLabel("Name", { exact: true }).fill(name);
		await form.getByRole("radio", { name: /Day job/ }).check();
		await form.getByRole("radio", { name: /Part time/ }).check();
		await form.getByLabel("Full-time week (hours)").fill(String(FULL_TIME_HOURS));
		await form.getByLabel("Percentage", { exact: true }).fill(String(PERCENT));
		// From this week's Monday, so every week the test opens is under the term.
		await form.getByLabel("Effective from", { exact: true }).fill(isoDate(monday));
		await form.getByLabel("Holiday region").selectOption("CH");
		await form.getByLabel(/Region within/).selectOption("ZH");
		await form.getByRole("button", { name: "Create project" }).click();

		// Creating it lands on its page.
		await expect(page).toHaveURL(/\/project\//);
		await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
		const projectUrl = page.url().split("?")[0];
		const standing = page.getByRole("region", { name: "Where you stand" });
		await expect(standing.getByText(/^as of /)).toBeVisible();

		// The coming Friday — this week's while it has not passed, else next
		// week's — or a later one when that Friday is a public holiday, which
		// has nothing to book.
		const today = new Date();
		today.setHours(12, 0, 0, 0);
		let friday = addDays(monday, today.getDay() === 6 || today.getDay() === 0 ? 11 : 4);
		const dialog = page.getByRole("dialog");
		let before = 0;
		for (let attempt = 0; ; attempt += 1) {
			const week = isoDate(addDays(friday, -4));
			await page.goto(`${projectUrl}?week=${week}`);
			const expected = expectedFigure(page);
			await expect(expected).toHaveText(/^\d+\.\d h$/);
			before = hoursIn(await expected.innerText());

			await page
				.getByRole("region", { name: "Time off" })
				.getByRole("button", { name: "+ Book" })
				.click();
			await dialog.getByLabel("From").fill(isoDate(friday));
			await dialog.getByLabel("Through").fill(isoDate(friday));
			if (!(await dialog.getByText(/^Nothing to book/).isVisible())) break;
			if (attempt >= 3) throw new Error("four Fridays in a row are public holidays");
			await dialog.getByRole("button", { name: "Cancel" }).click();
			friday = addDays(friday, 7);
		}

		// A day of vacation costs the week one day's hours, and the day says why.
		await expect(dialog.getByRole("button", { name: "Vacation" })).toHaveAttribute(
			"aria-pressed",
			"true",
		);
		await dialog.getByRole("button", { name: "Save" }).click();
		await expect(dialog).toBeHidden();
		const expected = expectedFigure(page);
		await expect(expected).toHaveText(`${(before - HOURS_PER_DAY).toFixed(1)} h`);
		const fridayRow = page
			.getByRole("region", { name: "Days" })
			.locator(`[data-day="${isoDate(friday)}"]`);
		await expect(fridayRow).toContainText("Vacation");

		// Taking it back through the dialog gives them back.
		await fridayRow.getByRole("button", { name: "Change" }).click();
		await dialog.getByRole("button", { name: "Remove" }).click();
		await expect(dialog).toBeHidden();
		await expect(expected).toHaveText(`${before.toFixed(1)} h`);
		await expect(fridayRow).not.toContainText("Vacation");

		// A change from three weeks on is planned; the first term stays in force.
		const register = page.getByRole("region", { name: "Contract" });
		const changeFrom = addDays(monday, 21);
		await register.getByRole("button", { name: /Change contract from/ }).click();
		await dialog.getByLabel("From").fill(isoDate(changeFrom));
		await dialog.getByLabel("Percentage", { exact: true }).fill("90");
		await dialog.getByRole("button", { name: "Save term" }).click();
		await expect(dialog).toBeHidden();
		const terms = register.getByRole("list", { name: "Terms" }).getByRole("listitem");
		await expect(terms).toHaveCount(2);
		await expect(terms.filter({ hasText: `From ${plainDate(monday)}` })).toContainText(/in force/i);
		await expect(terms.filter({ hasText: `From ${plainDate(changeFrom)}` })).toContainText(
			/planned/i,
		);
		await expect(register).toContainText(`Next → Part time · 90% of 40 h`);

		// Archive at the foot of the settings drawer, confirmed, and back to the dashboard.
		await page.getByRole("button", { name: "Project settings" }).click();
		const foot = page.getByRole("dialog").getByRole("region", { name: "Archive" });
		await foot.getByRole("button", { name: "Archive project" }).click();
		await foot.getByRole("button", { name: "Archive project" }).click();
		await expect(page).toHaveURL(/\/app$/);
	});
});
