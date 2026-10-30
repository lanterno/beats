import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";
// Imported by path, not through the `@/shared/config` barrel: the barrel reads
// `import.meta.env`, which does not exist while Vite loads this file.
import { APP_NAME } from "./client/shared/config/brand";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vitejs.dev/config/
export default defineConfig(() => ({
	server: {
		host: "::",
		port: 8080,
		fs: {
			allow: ["./client", "./"],
			deny: [".env", ".env.*", "*.{crt,pem}", "**/.git/**"],
		},
	},
	build: {
		outDir: "dist/spa",
	},
	plugins: [
		react(),
		// index.html cannot import the name, so it carries `%APP_NAME%` and this
		// fills it in, before Vite's own `%ENV%` pass sees the placeholder.
		{
			name: "app-name",
			transformIndexHtml: {
				order: "pre",
				handler: (html: string) => html.split("%APP_NAME%").join(APP_NAME),
			},
		},
		VitePWA({
			registerType: "autoUpdate",
			includeAssets: [
				"favicon.svg",
				"favicon.ico",
				"apple-touch-icon.png",
				"pwa-192.svg",
				"pwa-512.svg",
				"pwa-maskable-512.svg",
			],
			manifest: {
				name: `${APP_NAME} — Time Tracker`,
				short_name: APP_NAME,
				description: "Personal time tracking with insights, streaks, and a wall clock",
				theme_color: "#8CC1E2",
				background_color: "#E4F0F1",
				display: "standalone",
				start_url: "/",
				icons: [
					{
						src: "pwa-192.svg",
						sizes: "192x192",
						type: "image/svg+xml",
						purpose: "any",
					},
					{
						src: "pwa-512.svg",
						sizes: "512x512",
						type: "image/svg+xml",
						purpose: "any",
					},
					{
						// Full-bleed: a launcher that cuts its own shape would
						// otherwise show the tile's corners inside its own.
						src: "pwa-maskable-512.svg",
						sizes: "512x512",
						type: "image/svg+xml",
						purpose: "maskable",
					},
				],
			},
			workbox: {
				globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
				// Deletes the `api-cache` an older worker left on the device (see below).
				importScripts: ["sw-retired-caches.js"],
				// No rule here matches the API, on purpose, so the worker never sees an
				// /api/ request and every read goes to the network. A Cache Storage
				// entry is keyed by URL alone: it ignores the Authorization header and
				// outlives sign-out, so a cached read could answer whoever uses the
				// device next. It ignores Cache-Control too, so it would also keep the
				// public report (`/api/reports/`), which the API sends `no-store` so a
				// shared machine keeps no copy of a client's hours. Nothing offline
				// reads it either: the timer keeps its own state and queued writes wait
				// in IndexedDB (`shared/lib/mutationQueue.ts`).
				runtimeCaching: [
					{
						urlPattern: /^https?:\/\/fonts\.googleapis\.com\/.*/,
						handler: "CacheFirst",
						options: {
							cacheName: "google-fonts-stylesheets",
							expiration: {
								maxEntries: 10,
								maxAgeSeconds: 60 * 60 * 24 * 365,
							},
						},
					},
					{
						urlPattern: /^https?:\/\/fonts\.gstatic\.com\/.*/,
						handler: "CacheFirst",
						options: {
							cacheName: "google-fonts-webfonts",
							expiration: {
								maxEntries: 30,
								maxAgeSeconds: 60 * 60 * 24 * 365,
							},
						},
					},
				],
			},
		}),
	],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./client"),
		},
	},
}));
