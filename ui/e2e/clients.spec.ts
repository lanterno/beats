import { expect, type Locator, test } from "@playwright/test";

/**
 * The billing surfaces as they lay out, which jsdom cannot draw: the Clients
 * page's panel for the seeded client — its amount and the lines table it is
 * made of — and the Billing panel in the rail of the seeded freelance
 * project. `api/scripts/e2e_session.py` seeds both: a client at 85.00 EUR an
 * hour from 1 January, a project billable at that rate, and two finished
 * sessions in the last three hours (so this month has a line, unless the
 * month began less than three hours ago). Nothing here writes, so every run
 * reads the same seed.
 */

const CLIENT = "E2E Client";
const PROJECT = "E2E Client Work";

/** A box the browser actually drew: on the page, with room in it. */
async function expectDrawn(locator: Locator) {
	await expect(locator).toBeVisible();
	const box = await locator.boundingBox();
	expect(box?.width ?? 0).toBeGreaterThan(0);
	expect(box?.height ?? 0).toBeGreaterThan(0);
}

test.describe("Clients and billing", () => {
	test("the Clients page leads with the month and lays out the client's lines and amount", async ({
		page,
	}) => {
		await page.goto("/clients");

		const summary = page.getByRole("region", { name: "Summary" });
		await expect(summary).toContainText(/billable so far in \w+/);

		const panel = page.getByRole("region", { name: CLIENT });
		await expectDrawn(panel);
		// The rate in force today, from the seeded client's one term.
		await expect(panel).toContainText("€85.00/h since Jan 1");

		const table = panel.getByRole("table");
		await expectDrawn(table);
		const line = table.getByRole("row").filter({ hasText: PROJECT });
		await expect(line).toHaveCount(1);
		await expect(line).toContainText("client's rate");
		// A priced line: hours × €85.00, never nothing.
		const amount = line.getByRole("cell").last();
		await expect(amount).toHaveText(/^€\d[\d,]*\.\d\d$/);
		await expect(amount).not.toHaveText("€0.00");

		// The entries open under the table, each with its Billable pill.
		await panel.getByRole("button", { name: /^Entries \(\d+\)$/ }).click();
		const pill = panel.getByRole("switch", { name: /^Billable: / }).first();
		await expectDrawn(pill);
		await expect(pill).toHaveAttribute("aria-checked", "true");
	});

	test("the seeded freelance project's rail shows its billing", async ({ page }) => {
		await page.goto("/projects");
		await page.getByRole("link", { name: PROJECT }).first().click();
		await expect(page).toHaveURL(/\/project\//);

		const billing = page.getByRole("region", { name: "Billing" });
		await expectDrawn(billing);
		await expect(billing).toContainText(CLIENT);
		await expect(billing.getByRole("list", { name: "Billing terms" })).toContainText(
			"billable at the client's rate, €85.00/h",
		);
		await expect(billing).toContainText(/This month: [\d.]+ h billable · €/);
		await expect(billing.getByRole("link", { name: "→ Clients" })).toHaveAttribute(
			"href",
			"/clients",
		);
	});
});
