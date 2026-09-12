import { expect, type Locator, test } from "@playwright/test";

/**
 * A day job against its contract, end to end: create one through the form,
 * read the week card, book a day of vacation in the absence calendar and
 * watch the expectation drop by one day's hours, then take the day back.
 *
 * Every run creates its own project — the name carries the clock — so what
 * an earlier run left in the database never decides what this one sees.
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

/** Monday to Friday of the current week, at noon local time. */
function weekdaysOfThisWeek(): Date[] {
	const today = new Date();
	today.setHours(12, 0, 0, 0);
	const monday = new Date(today);
	monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
	return [0, 1, 2, 3, 4].map((offset) => {
		const d = new Date(monday);
		d.setDate(monday.getDate() + offset);
		return d;
	});
}

/** "25.6 h" → 25.6 */
function hoursIn(text: string): number {
	const match = /(-?\d+(?:\.\d+)?)\s*h/.exec(text);
	if (!match) throw new Error(`no hours in "${text}"`);
	return Number(match[1]);
}

/**
 * The first weekday of this week the calendar lets an absence be recorded
 * on — a public holiday is not a button. The calendar opens on the current
 * month; a week straddling a month boundary may need one step either way.
 */
async function bookableWeekday(calendar: Locator): Promise<{ button: Locator; day: number }> {
	const today = new Date();
	const monthsFromToday = (d: Date) =>
		(d.getFullYear() - today.getFullYear()) * 12 + d.getMonth() - today.getMonth();
	// Days on the month already shown first, so the common case needs no click.
	const candidates = weekdaysOfThisWeek().sort(
		(a, b) => Math.abs(monthsFromToday(a)) - Math.abs(monthsFromToday(b)),
	);
	let shown = 0;
	for (const date of candidates) {
		const wanted = monthsFromToday(date);
		while (shown < wanted) {
			await calendar.getByRole("button", { name: "Next month" }).click();
			shown += 1;
		}
		while (shown > wanted) {
			await calendar.getByRole("button", { name: "Previous month" }).click();
			shown -= 1;
		}
		const day = date.getDate();
		// The button's name is the long date and what is on it, in whatever
		// locale the browser spells the date; the day number is what we know.
		const button = calendar.getByRole("button", {
			name: new RegExp(`\\b${day}\\b.*record an absence$`),
		});
		if ((await button.count()) > 0) return { button, day };
	}
	throw new Error("every weekday of this week is a public holiday");
}

test.describe("Work contracts", () => {
	test("a day job's week follows the contract, and an absence lowers what it expects", async ({
		page,
	}) => {
		const name = `Day job ${Date.now()}`;
		const [monday] = weekdaysOfThisWeek();

		await page.goto("/app");
		await page.getByRole("button", { name: "New project" }).first().click();
		const form = page.getByRole("dialog", { name: "New project" });
		await form.getByLabel("Name", { exact: true }).fill(name);
		await form.getByRole("radio", { name: /Day job/ }).check();
		await form.getByRole("radio", { name: /Part time/ }).check();
		await form.getByLabel("Full-time week (hours)").fill(String(FULL_TIME_HOURS));
		await form.getByLabel("Percentage", { exact: true }).fill(String(PERCENT));
		// From this week's Monday, so the week on the card is under the term.
		await form.getByLabel("Effective from", { exact: true }).fill(isoDate(monday));
		await form.getByLabel("Holiday region").selectOption("CH");
		await form.getByLabel(/Region within/).selectOption("ZH");
		await form.getByRole("button", { name: "Create project" }).click();

		// Creating it lands on its page.
		await expect(page).toHaveURL(/\/project\//);
		await expect(page.getByRole("button", { name, exact: true })).toBeVisible();

		const card = page.getByRole("region", { name: "Week against the contract" });
		const expected = card
			.getByText("Expected", { exact: true })
			.locator("..")
			.getByRole("definition");
		await expect(expected).toHaveText(/^\d+\.\d h$/);
		await expect(card.getByText(/Balance as of today/)).toBeVisible();
		const before = hoursIn(await expected.innerText());

		// A day of vacation costs the week one day's hours.
		const calendar = page.getByRole("region", { name: "Absences" });
		const { button, day } = await bookableWeekday(calendar);
		await button.click();
		await page.getByRole("dialog").getByRole("button", { name: "Record absence" }).click();
		await expect(expected).toHaveText(`${(before - HOURS_PER_DAY).toFixed(1)} h`);

		// Taking it back gives them back.
		await calendar
			.getByRole("button", { name: new RegExp(`\\b${day}\\b.*Change or remove$`) })
			.click();
		await page.getByRole("dialog").getByRole("button", { name: "Remove" }).click();
		await expect(expected).toHaveText(`${before.toFixed(1)} h`);
	});
});
