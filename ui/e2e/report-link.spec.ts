import {
	type Browser,
	type BrowserContext,
	expect,
	type Page,
	type Request,
	test,
} from "@playwright/test";

/**
 * A report link end to end (docs/billing.md, *Report links (phase 1c)*):
 * made through the share dialog on the Clients page, opened by someone with
 * no session, and turned off again. `api/scripts/e2e_session.py` seeds the
 * client and two finished sessions on its billed project last month, 2.25 h
 * at €85.00, which the dialog's preselected *Last month* covers.
 *
 * What the unit tests cannot see is here: that the page served at
 * `/report#…` (the dev server's rewrite, as Firebase's and nginx's) loads
 * nothing from a third party and sends no session, that its tables are
 * drawn, that it fits a phone and prints as a document. Each test turns its
 * own link off, so the seed's client keeps no live link between runs.
 */

const CLIENT = "E2E Client";
const PAGE_ORIGIN = "http://localhost:8080";
const API_ORIGIN = "http://localhost:7999";
const DEAD =
	"This report link isn't valid. It may have been turned off or have ended, or the address may be incomplete.";

/** A link over last month with amounts, made through the dialog: its address and label. */
async function makeLink(page: Page): Promise<{ url: string; label: string }> {
	const label = `e2e-${Date.now()}`;
	await page.goto("/clients");
	const panel = page.getByRole("region", { name: CLIENT, exact: true });
	await panel.getByRole("button", { name: "Share", exact: true }).click();

	const dialog = page.getByRole("dialog", { name: `Share a report with ${CLIENT}` });
	await expect(dialog.getByRole("button", { name: "Last month" })).toHaveAttribute(
		"aria-pressed",
		"true",
	);
	await dialog.getByRole("checkbox", { name: /Show amounts/ }).check();
	// No expiry is chosen for you: Create waits for one.
	const create = dialog.getByRole("button", { name: "Create", exact: true });
	await expect(create).toBeDisabled();
	await dialog.getByRole("button", { name: "30 days" }).click();
	await dialog.getByLabel("Label").fill(label);
	// The preview is the report the client will read.
	await expect(dialog.getByRole("region", { name: "Preview" })).toContainText("€191.25");
	await create.click();

	const field = dialog.getByLabel("Report link");
	await expect(field).toHaveValue(/\/report#lpr_[A-Za-z0-9_-]{43}$/);
	const url = await field.inputValue();
	await dialog.getByRole("button", { name: "Copy" }).click();
	await dialog.getByRole("button", { name: "Done" }).click();
	await expect(dialog).toBeHidden();
	return { url, label };
}

/** Turns the labelled link off from the client's panel, answering its question. */
async function turnOff(page: Page, label: string) {
	await page.goto("/clients");
	const panel = page.getByRole("region", { name: CLIENT, exact: true });
	await panel.getByRole("button", { name: /^Report links \(\d+\)$/ }).click();
	await panel
		.getByRole("listitem")
		.filter({ hasText: label })
		.getByRole("button", { name: "Turn off" })
		.click();
	await page
		.getByRole("dialog", { name: "Turn off this report link?" })
		.getByRole("button", { name: "Turn off" })
		.click();
	await expect(panel.getByRole("listitem").filter({ hasText: label })).toHaveCount(0);
}

/** A browser with no session and no storage: the client's. */
function signedOut(browser: Browser): Promise<BrowserContext> {
	return browser.newContext({ storageState: { cookies: [], origins: [] } });
}

test.describe("Report links", () => {
	test("makes a link, opens it signed out, and turns it off", async ({ page, browser }) => {
		const { url, label } = await makeLink(page);

		const context = await signedOut(browser);
		const requests: Request[] = [];
		context.on("request", (request) => requests.push(request));
		const viewer = await context.newPage();
		try {
			await viewer.goto(url);
			await expect(viewer.getByRole("heading", { name: CLIENT, level: 1 })).toBeVisible();
			await expect(viewer.locator("main")).toContainText("2.25");
			await expect(viewer.locator("main")).toContainText("€191.25");
			await expect(viewer).toHaveTitle("Hours report");

			// The month's lines are drawn, not only in the DOM.
			const lines = viewer.getByRole("table", { name: /, by project$/ });
			await expect(lines).toBeVisible();
			expect((await lines.boundingBox())?.height ?? 0).toBeGreaterThan(0);

			// Only the page's own origin and the API: no font host, no tracker.
			for (const request of requests) {
				expect([PAGE_ORIGIN, API_ORIGIN]).toContain(new URL(request.url()).origin);
			}
			const reads = requests.filter((request) => request.url().endsWith("/api/public/reports"));
			expect(reads.length).toBeGreaterThan(0);
			for (const read of reads) expect((await read.allHeaders()).authorization).toBeUndefined();

			await turnOff(page, label);

			await viewer.reload();
			await expect(viewer.locator("main")).toContainText(DEAD);
			expect(await viewer.evaluate(() => document.body.innerText)).not.toContain(CLIENT);
		} finally {
			await context.close();
		}
	});

	test("fits a phone and prints as a document", async ({ page, browser }) => {
		const { url, label } = await makeLink(page);

		const context = await signedOut(browser);
		const viewer = await context.newPage();
		try {
			await viewer.setViewportSize({ width: 390, height: 844 });
			await viewer.goto(url);
			await expect(viewer.getByRole("heading", { name: CLIENT, level: 1 })).toBeVisible();
			const overflow = await viewer.evaluate(
				() => document.documentElement.scrollWidth - window.innerWidth,
			);
			expect(overflow).toBeLessThanOrEqual(0);

			// On screen the day rows are folded behind their button.
			const days = viewer.getByRole("table", { name: /, day by day$/ });
			await expect(days).toBeHidden();

			await viewer.emulateMedia({ media: "print" });
			await expect(viewer.getByRole("button", { name: "Print or save as PDF" })).toBeHidden();
			await expect(days).toBeVisible();
			expect((await days.boundingBox())?.height ?? 0).toBeGreaterThan(0);
			const ground = await viewer.evaluate(() => getComputedStyle(document.body).backgroundColor);
			expect(ground).toBe("rgb(255, 255, 255)");
		} finally {
			await context.close();
			await turnOff(page, label);
		}
	});

	test("a signed-in browser opening a link sends no session", async ({ page }) => {
		const { url, label } = await makeLink(page);
		try {
			const read = page.waitForRequest((request) => request.url().endsWith("/api/public/reports"));
			await page.goto(url);
			// The report, not the app's Not found.
			await expect(page.getByRole("heading", { name: CLIENT, level: 1 })).toBeVisible();
			expect((await (await read).allHeaders()).authorization).toBeUndefined();
		} finally {
			await turnOff(page, label);
		}
	});
});
