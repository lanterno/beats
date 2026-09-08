import { expect, test } from "@playwright/test";

test.describe("Insights", () => {
	test("page renders with header", async ({ page }) => {
		await page.goto("/insights");
		await expect(page.locator("text=Insights")).toBeVisible({ timeout: 10_000 });
	});

	test("contribution heatmap renders", async ({ page }) => {
		await page.goto("/insights");
		// The heatmap has no heading of its own; its year controls and the
		// less/more legend are what identify it on the page.
		await expect(page.getByRole("button", { name: "Previous year" })).toBeVisible({
			timeout: 10_000,
		});
		await expect(page.getByText("Less", { exact: true })).toBeVisible();
		await expect(page.getByText("More", { exact: true })).toBeVisible();
	});

	test("tag filter is present", async ({ page }) => {
		await page.goto("/insights");
		// The filter is a <select> that only renders once at least one session
		// carries a tag — which is why the suite seeds one.
		const filter = page.getByRole("combobox").first();
		await expect(filter).toBeVisible({ timeout: 10_000 });
		await expect(filter).toContainText("All Tags");
	});

	test("monthly summary stats render", async ({ page }) => {
		await page.goto("/insights");
		// The page should show monthly stats like hours, sessions, or active days
		const statsArea = page.locator("text=/hours|sessions|active days|This Month/i").first();
		await expect(statsArea).toBeVisible({ timeout: 10_000 });
	});

	test("digests link is present", async ({ page }) => {
		await page.goto("/insights");
		const digestsLink = page.locator('a[href="/insights/digests"]');
		await expect(digestsLink).toBeVisible({ timeout: 10_000 });
	});

	test("navigates to digests page", async ({ page }) => {
		await page.goto("/insights/digests");
		await expect(page.getByRole("heading", { name: /digests?/i }).first()).toBeVisible({
			timeout: 10_000,
		});
	});

	test("weekly card section renders", async ({ page }) => {
		await page.goto("/insights");
		// Scroll down to find the weekly card section
		const weeklySection = page.locator("text=/Weekly|Share|week/i").first();
		await expect(weeklySection).toBeVisible({ timeout: 10_000 });
	});
});
