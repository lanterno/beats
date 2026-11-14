import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
// By path, not a barrel: vite.config loads before import.meta.env exists.
import { APP_NAME } from "./client/shared/config/brand";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// The back office is served by the operator app itself in production
// (operator_server.py mounts the build), so the bundle names no API origin:
// every call is same-origin. Locally Vite serves it on :8081 and proxies
// /api/operator to `just run-operator-locally` on :7998.
//
// Both are overridable, because two checkouts of this repo on one machine
// otherwise fight over the pair — and the operator API refuses a write whose
// Origin is not its own, so a dev server that silently moved to :8082 reads
// fine and cannot act. Set OPERATOR_ORIGIN to match when you move the port.
const PORT = Number(process.env.BACKOFFICE_PORT ?? 8081);
const OPERATOR_API = process.env.BACKOFFICE_OPERATOR_API ?? "http://localhost:7998";

export default defineConfig(() => ({
	server: {
		host: "::",
		// Rather than stepping to the next free port, which the API's Origin
		// check would then refuse every write from.
		strictPort: true,
		port: PORT,
		proxy: {
			"/api/operator": OPERATOR_API,
		},
	},
	build: {
		// Into the API image: the Dockerfile's existing `COPY src/` carries it
		// (docs/backoffice.md § Deployment). Gitignored there.
		outDir: "../api/src/beats/operator/static",
		emptyOutDir: true,
	},
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./client"),
		},
	},
	plugins: [
		react(),
		{
			name: "app-name",
			transformIndexHtml: {
				order: "pre" as const,
				handler: (html: string) => html.split("%APP_NAME%").join(APP_NAME),
			},
		},
	],
}));
