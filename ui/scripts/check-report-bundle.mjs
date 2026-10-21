#!/usr/bin/env node
/**
 * Fails the build if the report page reaches the app, a third party or the
 * service worker (docs/billing.md, *The public page*).
 *
 * The page's CSP (ui/firebase.json, ui/nginx.conf) allows only same-origin
 * scripts, styles and fonts and one API, and refuses inline script and
 * style. This reads what `vite build` wrote to dist/spa and proves the
 * properties that CSP relies on, every time the bundle is built: dev cannot,
 * since the dev server injects an inline React Refresh preamble the CSP
 * refuses.
 *
 * - report.html: its title, no inline <script> or style, no other origin in
 *   a src or href, no Open Graph or Twitter meta, no Plausible, no
 *   registerSW, and no link but the PWA plugin's manifest, which the CSP's
 *   manifest-src allows.
 * - every JS and CSS file reachable from it (its src, its href links, and
 *   the imports inside those chunks, followed): none of the session's key,
 *   an Authorization header, Google Fonts, Plausible or the worker.
 * - every @font-face url() in that CSS: a same-origin /assets/ .woff2 or
 *   .woff, never a data: URI (which font-src 'self' refuses) or another
 *   origin. local() faces are fine.
 *
 * Exits 1 naming the first violation. No dependencies: node only.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIST = fileURLToPath(new URL("../dist/spa/", import.meta.url));
const MANIFEST_LINK = '<link rel="manifest" href="/manifest.webmanifest">';
const FORBIDDEN = [
	"beats_session_token",
	"Authorization",
	"fonts.googleapis.com",
	"fonts.gstatic.com",
	"plausible.io",
	"registerSW",
	"workbox",
];

function fail(message) {
	console.error(`check-report-bundle: ${message}`);
	process.exit(1);
}

const htmlPath = path.join(DIST, "report.html");
if (!existsSync(htmlPath)) fail("dist/spa/report.html is missing; run vite build first");
// Comments say what the shell leaves out; only markup is checked. Removed
// until none is left, so one comment cannot hide inside another, and a
// comment left open fails rather than hiding what follows it.
let html = readFileSync(htmlPath, "utf8");
for (let prev = ""; prev !== html; ) {
	prev = html;
	html = html.replace(/<!--[\s\S]*?-->/g, "");
}
if (html.includes("<!--")) fail("report.html has a comment left open");

if (!html.includes("<title>Hours report</title>")) fail("report.html's title is not Hours report");
for (const tag of html.match(/<script\b[^>]*>/gi) ?? []) {
	if (!/\ssrc\s*=/i.test(tag)) fail(`report.html has an inline script: ${tag}`);
}
if (/<style\b/i.test(html)) fail("report.html has a <style> element");
if (/\sstyle="/i.test(html)) fail("report.html has an inline style attribute");
for (const [, attr, url] of html.matchAll(/\s(src|href)\s*=\s*["']?([^"'\s>]*)/gi)) {
	if (/^(https?:)?\/\//i.test(url)) fail(`report.html's ${attr} names another origin: ${url}`);
}
if (/<meta[^>]+(property|name)="(og|twitter):/i.test(html)) {
	fail("report.html has Open Graph or Twitter meta");
}
if (/plausible/i.test(html)) fail("report.html names Plausible");
if (/registerSW/i.test(html)) fail("report.html registers the service worker");
for (const tag of html.match(/<link\b[^>]*rel=["']?manifest[^>]*>/gi) ?? []) {
	if (tag !== MANIFEST_LINK) fail(`report.html has an unexpected manifest link: ${tag}`);
}

/** A same-origin asset reference, as a path under dist/spa, or null. */
function local(url, from) {
	if (/^(https?:)?\/\//i.test(url) || url.startsWith("data:")) return null;
	const clean = url.split(/[?#]/)[0];
	return clean.startsWith("/") ? path.join(DIST, clean) : path.resolve(path.dirname(from), clean);
}

const queue = [];
for (const [, url] of html.matchAll(/\s(?:src|href)\s*=\s*["']?([^"'\s>]*\.(?:js|css))/gi)) {
	queue.push(local(url, htmlPath));
}

const seen = new Set();
const css = [];
while (queue.length > 0) {
	const file = queue.pop();
	if (!file || seen.has(file)) continue;
	seen.add(file);
	if (!existsSync(file)) fail(`report.html reaches ${path.relative(DIST, file)}, which is missing`);
	const text = readFileSync(file, "utf8");
	const name = path.relative(DIST, file);
	for (const word of FORBIDDEN) {
		if (text.includes(word)) fail(`${name}, reached from report.html, contains "${word}"`);
	}
	if (file.endsWith(".css")) {
		css.push([name, text]);
		for (const [, url] of text.matchAll(/@import\s+(?:url\()?["']?([^"')\s;]+)/g)) {
			queue.push(local(url, file));
		}
		continue;
	}
	// Static imports (`from"./x.js"`, `import"./x.js"`) and dynamic ones.
	for (const [, spec] of text.matchAll(/(?:from|import)\s*\(?\s*["'](\.{1,2}\/[^"']+\.js)["']/g)) {
		queue.push(path.resolve(path.dirname(file), spec));
	}
}

for (const [name, text] of css) {
	for (const [face] of text.matchAll(/@font-face\s*\{[^}]*\}/g)) {
		for (const [, raw] of face.matchAll(/url\(\s*([^)]*?)\s*\)/g)) {
			const url = raw.replace(/^["']|["']$/g, "");
			if (!/^\/assets\/[^/]+\.woff2?$/.test(url)) {
				fail(
					`${name} has a font face that is not a same-origin .woff2 or .woff: ${url.slice(0, 80)}`,
				);
			}
		}
	}
}

console.log(
	`check-report-bundle: report.html and its ${seen.size} files reach nothing they must not`,
);
