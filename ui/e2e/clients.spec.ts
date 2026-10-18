import { expect, type Locator, type Page, test } from "@playwright/test";

/**
 * The billing surfaces as they lay out, which jsdom cannot draw: the Clients
 * page's panel for the seeded client — its amount and the lines table it is
 * made of — and the Billing panel in the rail of the seeded freelance
 * project. `api/scripts/e2e_session.py` seeds both: a client at 85.00 EUR an
 * hour from 1 January, a project billable at that rate, and two finished
 * sessions in the last three hours (so this month has a line, unless the
 * month began less than three hours ago). It also seeds two billing budgets:
 * 40 hours a month on the client, and €200.00 in total since 1 January on
 * the project. Nothing here writes, so every run reads the same seed.
 */

const CLIENT = "E2E Client";
const PROJECT = "E2E Client Work";

/** A desktop window, and a phone held upright. */
const WIDTHS = [1280, 390] as const;

/** A box the browser actually drew: on the page, with room in it. */
async function expectDrawn(locator: Locator) {
	await expect(locator).toBeVisible();
	const box = await locator.boundingBox();
	expect(box?.width ?? 0).toBeGreaterThan(0);
	expect(box?.height ?? 0).toBeGreaterThan(0);
}

/** Nothing on the page is wider than the window, so it never scrolls sideways. */
async function expectNoSidewaysScroll(page: Page) {
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - window.innerWidth,
	);
	expect(overflow).toBeLessThanOrEqual(0);
}

test.describe("Clients and billing", () => {
	test("the Clients page leads with the month and lays out the client's lines and amount", async ({
		page,
	}) => {
		await page.goto("/clients");

		const summary = page.getByRole("region", { name: "Summary" });
		await expect(summary).toContainText(/billable so far in \w+/);

		// Exact: the panel holds a region of its own, "E2E Client's budgets".
		const panel = page.getByRole("region", { name: CLIENT, exact: true });
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
		// The month's line's; the client's budget line below it has one too.
		await expect(billing.getByRole("link", { name: "→ Clients" }).first()).toHaveAttribute(
			"href",
			"/clients",
		);
	});

	test("the client's billing budgets lay out at desktop and phone width", async ({ page }) => {
		for (const width of WIDTHS) {
			await test.step(`${width} px`, async () => {
				await page.setViewportSize({ width, height: 900 });
				await page.goto("/clients");

				const budgets = page.getByRole("region", { name: `${CLIENT}'s budgets` });
				await expectDrawn(budgets);
				// The client's own budget, then its project's: a sentence and a meter each.
				await expect(budgets).toContainText(/of 40 h this month/);
				await expect(budgets).toContainText(/of €200\.00 since Jan 1/);
				await expectDrawn(budgets.getByRole("meter", { name: `${CLIENT}'s budget` }));
				await expectDrawn(budgets.getByRole("meter", { name: `${PROJECT}'s budget` }));
				await expectNoSidewaysScroll(page);
			});
		}
	});

	test("the project's billing budget lays out in its Billing panel at desktop and phone width", async ({
		page,
	}) => {
		for (const width of WIDTHS) {
			await test.step(`${width} px`, async () => {
				await page.setViewportSize({ width, height: 900 });
				await page.goto("/projects");
				await page.getByRole("link", { name: PROJECT }).first().click();
				await expect(page).toHaveURL(/\/project\//);

				const billing = page.getByRole("region", { name: "Billing" });
				await expectDrawn(billing);
				await expect(billing).toContainText(/of €200\.00 since Jan 1/);
				await expectDrawn(billing.getByRole("meter", { name: `${PROJECT}'s budget` }));
				// The client's budget, read-only here: this project counts toward it too.
				await expect(billing).toContainText(`Also counts toward ${CLIENT}'s budget:`);
				await expectNoSidewaysScroll(page);
			});
		}
	});
});
