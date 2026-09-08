import { execFileSync } from "node:child_process";
import { test as setup } from "@playwright/test";

/**
 * Signs the suite in before anything else runs.
 *
 * The specs below all live behind `ProtectedRoute`, which needs a session token
 * in localStorage. Sessions normally come from a WebAuthn passkey ceremony that
 * a headless browser cannot perform, so the token is minted by the API's own
 * SessionManager — `api/scripts/e2e_session.py` — and planted here.
 *
 * The application is untouched by this: the token is an ordinary session, and
 * everything downstream validates it exactly as it would a real one.
 */
export const STORAGE_STATE = "e2e/.auth/state.json";

setup("authenticate", async ({ page, context }) => {
	const raw = execFileSync("uv", ["run", "python", "scripts/e2e_session.py"], {
		cwd: "../api",
		encoding: "utf8",
		env: process.env,
	});
	const { token } = JSON.parse(raw.trim()) as { token: string };

	// The origin has to exist before localStorage can be written to it.
	await page.goto("/");
	await page.evaluate((value) => {
		window.localStorage.setItem("beats_session_token", value);
	}, token);

	await context.storageState({ path: STORAGE_STATE });
});
