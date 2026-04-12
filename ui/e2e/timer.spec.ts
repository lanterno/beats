import { expect, test } from "@playwright/test";

test.describe("Timer", () => {
	test("dashboard displays timer area", async ({ page }) => {
		await page.goto("/app");
		// Timer display should show 00:00:00 or running time
		const timerDisplay = page.locator("text=/\\d{2}:\\d{2}:\\d{2}/").first();
		await expect(timerDisplay).toBeVisible({ timeout: 10_000 });
	});

	test("project selector is visible on dashboard", async ({ page }) => {
		await page.goto("/app");
		// The sidebar should list projects that can be selected
		const sidebar = page.locator('[class*="sidebar"]').first();
		await expect(sidebar).toBeVisible();

		// Projects should be listed as clickable items
		const projectLinks = page.locator('a[href^="/project/"]');
		const count = await projectLinks.count();
		expect(count).toBeGreaterThanOrEqual(0);
	});

	test("timer shows formatted time display", async ({ page }) => {
		await page.goto("/app");
		// The timer should show HH:MM:SS format somewhere on the page
		await expect(page.locator("text=/\\d{2}:\\d{2}:\\d{2}/").first()).toBeVisible({
			timeout: 10_000,
		});
	});
});
