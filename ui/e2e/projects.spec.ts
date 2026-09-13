import { expect, test } from "@playwright/test";

test.describe("Projects", () => {
	test("sidebar lists projects", async ({ page }) => {
		await page.goto("/app");
		const sidebar = page.locator('[class*="sidebar"]').first();
		await expect(sidebar).toBeVisible();
	});

	test("project detail page shows the open week's days", async ({ page }) => {
		await page.goto("/app");
		const projectLink = page.locator('a[href^="/project/"]').first();

		if (await projectLink.isVisible({ timeout: 5_000 }).catch(() => false)) {
			await projectLink.click();
			await expect(page.getByRole("region", { name: "Days" })).toBeVisible({ timeout: 10_000 });
		}
	});

	test("project detail page shows sessions", async ({ page }) => {
		await page.goto("/app");
		const projectLink = page.locator('a[href^="/project/"]').first();

		if (await projectLink.isVisible({ timeout: 5_000 }).catch(() => false)) {
			await projectLink.click();
			// The open week's days, with their sessions or the empty line.
			const days = page.getByRole("region", { name: "Days" });
			await expect(days).toBeVisible({ timeout: 10_000 });
			await expect(days.getByText(/session|No sessions yet/).first()).toBeVisible();
		}
	});

	test("can navigate between projects", async ({ page }) => {
		await page.goto("/app");
		const projectLinks = page.locator('a[href^="/project/"]');
		const count = await projectLinks.count();

		if (count >= 2) {
			// Click first project
			await projectLinks.first().click();
			await expect(page.getByRole("region", { name: "Days" })).toBeVisible({ timeout: 10_000 });
			const firstUrl = page.url();

			// Go back and click second project
			await page.goto("/app");
			await projectLinks.nth(1).click();
			await expect(page.getByRole("region", { name: "Days" })).toBeVisible({ timeout: 10_000 });
			expect(page.url()).not.toBe(firstUrl);
		}
	});
});
