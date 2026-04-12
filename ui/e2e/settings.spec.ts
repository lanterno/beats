import { expect, test } from "@playwright/test";

test.describe("Settings", () => {
	test("page renders with title", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Settings")).toBeVisible();
	});

	test("theme selector shows all themes", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Theme")).toBeVisible();

		for (const theme of ["Ember", "Midnight", "Forest", "Mono", "Sunset"]) {
			await expect(page.locator(`text=${theme}`)).toBeVisible();
		}
	});

	test("density selector shows all options", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Layout Density")).toBeVisible();

		for (const density of ["Comfortable", "Compact", "Spacious"]) {
			await expect(page.locator(`text=${density}`)).toBeVisible();
		}
	});

	test("clicking a theme applies it", async ({ page }) => {
		await page.goto("/settings");

		await page.locator("text=Midnight").click();

		const dataTheme = await page.locator("html").getAttribute("data-theme");
		expect(dataTheme).toBe("midnight");
	});

	test("clicking a density applies it", async ({ page }) => {
		await page.goto("/settings");

		await page.locator("text=Compact").click();

		const dataDensity = await page.locator("html").getAttribute("data-density");
		expect(dataDensity).toBe("compact");
	});

	test("data export section is present", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Data Export")).toBeVisible();
		await expect(page.locator("text=Sessions CSV")).toBeVisible();
		await expect(page.locator("text=Full JSON Backup")).toBeVisible();
	});

	test("data import section is present", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Data Import")).toBeVisible();
	});

	test("webhooks section is present", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Webhooks")).toBeVisible();
	});

	test("developer section shows API info", async ({ page }) => {
		await page.goto("/settings");
		await expect(page.locator("text=Developer")).toBeVisible();
		await expect(page.locator("text=API Base URL")).toBeVisible();
	});

	test("theme persists after navigation", async ({ page }) => {
		await page.goto("/settings");
		await page.locator("text=Forest").click();

		// Navigate away and back
		await page.goto("/app");
		await page.goto("/settings");

		const dataTheme = await page.locator("html").getAttribute("data-theme");
		expect(dataTheme).toBe("forest");
	});
});
