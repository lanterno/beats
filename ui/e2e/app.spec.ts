import { expect, test } from "@playwright/test";

test.describe("Beats App", () => {
	test("loads the dashboard", async ({ page }) => {
		await page.goto("/app");
		await expect(page).toHaveTitle(/Beats/);
	});

	test("sidebar shows project list", async ({ page }) => {
		await page.goto("/app");
		// The sidebar should render with at least one project or the empty state
		const sidebar = page.locator('[class*="sidebar"]').first();
		await expect(sidebar).toBeVisible();
	});

	test("navigates to insights page", async ({ page }) => {
		await page.goto("/insights");
		await expect(page.locator("text=Contribution")).toBeVisible({ timeout: 10_000 });
	});

	test("navigates to settings page", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Settings")).toBeVisible();
	});

	test("project detail page loads", async ({ page }) => {
		await page.goto("/app");
		// Click the first project link in the sidebar
		const projectLink = page.locator('a[href^="/projects/"]').first();
		if (await projectLink.isVisible()) {
			await projectLink.click();
			await expect(page.locator("text=This Week")).toBeVisible({ timeout: 10_000 });
		}
	});
});
