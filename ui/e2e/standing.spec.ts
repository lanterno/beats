import { expect, type Page, test } from "@playwright/test";

/**
 * The standing's two states the unit tests reach only through props: a week
 * that has not started yet, and the ledger failing to load. Both run on the
 * seeded side project, whose page reads `/ledger` for every closed-week claim.
 */

/** A local calendar date as the URL's `?week=` spells it. */
function isoDate(d: Date): string {
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, "0");
	const day = String(d.getDate()).padStart(2, "0");
	return `${y}-${m}-${day}`;
}

/** Next week's Monday, at noon local time. */
function nextMonday(): Date {
	const d = new Date();
	d.setHours(12, 0, 0, 0);
	d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + 7);
	return d;
}

/** The seeded project's page, reached the way a person reaches it. */
async function openSeededProject(page: Page): Promise<string> {
	await page.goto("/projects");
	await page
		.getByRole("link", { name: /E2E Project/ })
		.first()
		.click();
	await expect(page).toHaveURL(/\/project\//);
	return page.url().split("?")[0];
}

test.describe("Standing", () => {
	test("a week still to come gets its figures and no verdict", async ({ page }) => {
		const url = await openSeededProject(page);
		await page.goto(`${url}?week=${isoDate(nextMonday())}`);

		const standing = page.getByRole("region", { name: "Where you stand" });
		await expect(standing.getByText("Worked", { exact: true })).toBeVisible();
		await expect(standing).toContainText(/Week \d+/);
		await expect(standing).not.toContainText("This week");
		// Nothing is said about how a week closed, or what it has to go, before it opens.
		await expect(standing).not.toContainText("closed");
		await expect(standing).not.toContainText("to go");
	});

	test("says why the earlier weeks failed to load, and claims none closed", async ({ page }) => {
		await page.route("**/api/projects/*/ledger*", (route) =>
			route.fulfill({
				status: 503,
				json: { detail: "The ledger is down for this test", code: "SERVICE_UNAVAILABLE" },
			}),
		);
		await openSeededProject(page);

		// The error surfaces beside the weeks it affects — the Earlier weeks
		// panel — while Standing claims nothing it cannot know.
		// Two retries back off for about three seconds before the query gives up.
		const weeks = page.getByRole("region", { name: /Earlier weeks/ });
		await expect(weeks.getByRole("alert")).toHaveText("The ledger is down for this test", {
			timeout: 10_000,
		});
		const standing = page.getByRole("region", { name: "Where you stand" });
		await expect(standing).not.toContainText("No weeks closed yet");
		await expect(standing).not.toContainText(/Goal met \d+ of/);
	});
});
