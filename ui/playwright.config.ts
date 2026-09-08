import { defineConfig } from "@playwright/test";

const STORAGE_STATE = "e2e/.auth/state.json";

export default defineConfig({
	testDir: "./e2e",
	timeout: 30_000,
	retries: 0,
	use: {
		baseURL: "http://localhost:8080",
		headless: true,
	},
	projects: [
		// Mints a session first; every spec then starts signed in. Without it the
		// pages behind ProtectedRoute redirect to the homepage and the suite
		// tests an empty screen.
		{ name: "setup", testMatch: /auth\.setup\.ts/ },
		{
			name: "chromium",
			use: { browserName: "chromium", storageState: STORAGE_STATE },
			dependencies: ["setup"],
			testIgnore: /auth\.setup\.ts/,
		},
	],
	webServer: {
		command: "pnpm dev",
		url: "http://localhost:8080",
		reuseExistingServer: true,
		timeout: 15_000,
	},
});
