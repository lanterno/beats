import { expect, test } from "@playwright/test";

test.describe("Insights", () => {
	test("page renders with header", async ({ page }) => {
		await page.goto("/insights");
		await expect(page.locator("text=Insights")).toBeVisible({ timeout: 10_000 });
	});

	test("contribution heatmap renders", async ({ page }) => {
		await page.goto("/insights");
		await expect(page.locator("text=Contribution")).toBeVisible({ timeout: 10_000 });
	});

	test("project filter dropdown is present", async ({ page }) => {
		await page.goto("/insights");
		// The page should have a project filter or "All Projects" option
		const filter = page.locator("select, [role='combobox'], text=/All Projects|Filter/i").first();
		await expect(filter).toBeVisible({ timeout: 10_000 });
	});

	test("monthly summary stats render", async ({ page }) => {
		await page.goto("/insights");
		// The page should show monthly stats like hours, sessions, or active days
		const statsArea = page
			.locator("text=/hours|sessions|active days|This Month/i")
			.first();
		await expect(statsArea).toBeVisible({ timeout: 10_000 });
	});

	test("digests link is present", async ({ page }) => {
		await page.goto("/insights");
		const digestsLink = page.locator('a[href="/insights/digests"]');
		await expect(digestsLink).toBeVisible({ timeout: 10_000 });
	});

	test("navigates to digests page", async ({ page }) => {
		await page.goto("/insights/digests");
		await expect(page.locator("text=/Digest|digest/")).toBeVisible({ timeout: 10_000 });
	});

	test("weekly card section renders", async ({ page }) => {
		await page.goto("/insights");
		// Scroll down to find the weekly card section
		const weeklySection = page.locator("text=/Weekly|Share|week/i").first();
		await expect(weeklySection).toBeVisible({ timeout: 10_000 });
	});
});
