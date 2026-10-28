import { expect, test } from "@playwright/test";

/**
 * The marketing page's pricing section (docs/pricing.md): the decided price
 * shown struck through while the beta's 100% discount applies. Signed out,
 * since the marketing page is where a buyer reads it — a session would
 * route to the app instead.
 */
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Pricing on the marketing page", () => {
	test("the beta shows the real price, struck", async ({ page }) => {
		await page.goto("/");
		const pricing = page.getByRole("region", { name: "Pricing" });
		await expect(pricing).toBeVisible();
		// The struck €8 and the discount sit together: the price is known
		// before it is ever charged.
		await expect(pricing.locator("s", { hasText: "€8" })).toBeVisible();
		await expect(pricing.getByText("Free during beta")).toBeVisible();
		await expect(pricing.getByText("free up to 5 seats", { exact: false })).toBeVisible();
	});
});
