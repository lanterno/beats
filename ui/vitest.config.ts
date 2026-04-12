import { defineConfig } from "vitest/config";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./client"),
			"@shared": path.resolve(__dirname, "./shared"),
		},
	},
	test: {
		include: ["client/**/*.test.ts", "client/**/*.test.tsx"],
		environment: "jsdom",
		setupFiles: ["./vitest.setup.ts"],
	},
});
