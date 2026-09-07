import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./client"),
		},
	},
	test: {
		include: ["client/**/*.test.ts", "client/**/*.test.tsx"],
		environment: "jsdom",
		setupFiles: ["./vitest.setup.ts"],
	},
});
