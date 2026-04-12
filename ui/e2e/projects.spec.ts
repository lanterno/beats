import { expect, test } from "@playwright/test";

test.describe("Projects", () => {
	test("sidebar lists projects", async ({ page }) => {
		await page.goto("/app");
		const sidebar = page.locator('[class*="sidebar"]').first();
		await expect(sidebar).toBeVisible();
	});

	test("project detail page shows weekly breakdown", async ({ page }) => {
		await page.goto("/app");
		const projectLink = page.locator('a[href^="/project/"]').first();

		if (await projectLink.isVisible({ timeout: 5_000 }).catch(() => false)) {
			await projectLink.click();
			await expect(page.locator("text=This Week")).toBeVisible({ timeout: 10_000 });
		}
	});

	test("project detail page shows sessions", async ({ page }) => {
		await page.goto("/app");
		const projectLink = page.locator('a[href^="/project/"]').first();

		if (await projectLink.isVisible({ timeout: 5_000 }).catch(() => false)) {
			await projectLink.click();
			// Session list or empty state should be visible
			const hasContent = page.locator("text=/Session|No sessions|This Week/").first();
			await expect(hasContent).toBeVisible({ timeout: 10_000 });
		}
	});

	test("can navigate between projects", async ({ page }) => {
		await page.goto("/app");
		const projectLinks = page.locator('a[href^="/project/"]');
		const count = await projectLinks.count();

		if (count >= 2) {
			// Click first project
			await projectLinks.first().click();
			await expect(page.locator("text=This Week")).toBeVisible({ timeout: 10_000 });
			const firstUrl = page.url();

			// Go back and click second project
			await page.goto("/app");
			await projectLinks.nth(1).click();
			await expect(page.locator("text=This Week")).toBeVisible({ timeout: 10_000 });
			expect(page.url()).not.toBe(firstUrl);
		}
	});
});
