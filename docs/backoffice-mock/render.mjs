/**
 * Draw every `source/*.dc.html` into `screens/*.png`.
 *
 * The files were written for a design tool whose renderer, `support.js`, is
 * Anthropic's and was deliberately not copied here. This is a small renderer
 * of our own for the same four constructs, so the pictures can be redrawn
 * from the sources in this repo:
 *
 *   {{path}}                    filled from renderVals(), dotted, in text and
 *                               in attribute values
 *   <sc-for list="{{xs}}" as="x">   repeats its children, `x` in scope
 *   <sc-if value="{{x}}">       keeps its children when `x` is truthy
 *   <dc-import name="X" a="b">  renders X.dc.html with {a: "b"} as its props
 *
 * `hint-…` attributes are the design tool's layout hints and are dropped.
 * A `<helmet>` goes to the document head. Props come from the importer, or
 * from the `default` in the file's own `data-props`.
 *
 * Usage (Playwright comes from ui/'s install — this folder has none of its
 * own, and goes away when the stages ship):
 *
 *   node docs/backoffice-mock/render.mjs            # every screen
 *   node docs/backoffice-mock/render.mjs Jobs Audit # just these
 *
 * Like `scripts/gen_icons.py`, it has no `--check`: run it after editing a
 * source and commit what it wrote. A check would have to be a byte compare,
 * and text rasterization differs enough between machines to fail one on a
 * picture nobody changed — the output is deterministic on any one machine,
 * and about 0.1% of pixels move between two.
 *
 * Sizes come from `source/canvas.json`, which is also the design tool's, so
 * a board resized there resizes the picture here. Boards say `expand: fill`,
 * meaning the frame grows to its content, so each is shot full-page and the
 * height in canvas.json is a minimum.
 */

import { readFile, readdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { basename, dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(HERE, "source");
const SCREENS = join(HERE, "screens");

// Playwright is ui/'s dev dependency; nothing is installed in docs/.
const require = createRequire(join(HERE, "..", "..", "ui", "package.json"));
let chromium;
try {
	({ chromium } = require("@playwright/test"));
} catch {
	console.error("Playwright is missing. Run `pnpm install` in ui/ first.");
	process.exit(1);
}

const TYPES = {
	".html": "text/html; charset=utf-8",
	".css": "text/css; charset=utf-8",
	".json": "application/json; charset=utf-8",
	".js": "text/javascript; charset=utf-8",
};

/**
 * The renderer, as source to inject: it runs in the page, in place of the
 * `./support.js` every file asks for.
 */
const SUPPORT = `
window.DCLogic = class DCLogic {
	constructor(props) { this.props = props; }
	renderVals() { return {}; }
};

const HINT = /^hint-/;
const HANDLER = /^on[a-z]+$/;
const BOOLEAN = new Set(["checked", "disabled", "selected", "open", "readonly", "hidden"]);

/** The literals a {{…}} can hold instead of a path, as \`disabled="{{true}}"\`. */
const LITERAL = { true: true, false: false, null: null };

/** A dotted path, innermost loop variable first, then the file's values. */
function resolve(path, scopes) {
	const parts = path.trim().split(".");
	if (parts.length === 1 && Object.hasOwn(LITERAL, parts[0])) return LITERAL[parts[0]];
	for (let i = scopes.length - 1; i >= 0; i--) {
		if (Object.hasOwn(scopes[i], parts[0])) {
			let value = scopes[i][parts[0]];
			for (const part of parts.slice(1)) {
				if (value === undefined || value === null) return undefined;
				value = value[part];
			}
			return value;
		}
	}
	return undefined;
}

function fill(text, scopes) {
	return text.replace(/\\{\\{([^}]+)\\}\\}/g, (_, path) => {
		const value = resolve(path, scopes);
		return value === undefined || value === null || value === false ? "" : String(value);
	});
}

/** The one path in a {{…}} that is the whole value, for lists and tests. */
function sole(attr, scopes) {
	const match = /^\\s*\\{\\{([^}]+)\\}\\}\\s*$/.exec(attr ?? "");
	return match ? resolve(match[1], scopes) : attr;
}

async function load(name) {
	const response = await fetch(name + ".dc.html");
	if (!response.ok) throw new Error("no such import: " + name);
	const doc = new DOMParser().parseFromString(await response.text(), "text/html");
	const script = doc.querySelector("script[data-dc-script]");
	const declared = JSON.parse(script?.dataset.props ?? "{}");
	const defaults = {};
	for (const [key, spec] of Object.entries(declared)) {
		if (key !== "$preview" && spec && typeof spec === "object") defaults[key] = spec.default;
	}
	const Component = new Function("DCLogic", (script?.textContent ?? "") + "\\nreturn Component;")(
		window.DCLogic,
	);
	return { doc, defaults, Component };
}

/** One file, rendered into a fragment, with its helmet hoisted to the head. */
async function render(name, props) {
	const { doc, defaults, Component } = await load(name);
	const vals = new Component({ ...defaults, ...props }).renderVals();
	const root = doc.querySelector("x-dc");
	for (const helmet of root.querySelectorAll("helmet")) {
		for (const node of [...helmet.childNodes]) document.head.append(document.importNode(node, true));
		helmet.remove();
	}
	const fragment = document.createDocumentFragment();
	for (const node of [...root.childNodes]) fragment.append(document.importNode(node, true));
	await walk(fragment, [vals]);
	return fragment;
}

/** Expand every construct inside a node, in document order. */
async function walk(node, scopes) {
	for (const child of [...node.childNodes]) {
		if (child.nodeType === Node.TEXT_NODE) {
			if (child.nodeValue.includes("{{")) child.nodeValue = fill(child.nodeValue, scopes);
			continue;
		}
		if (child.nodeType !== Node.ELEMENT_NODE) continue;
		const tag = child.tagName.toLowerCase();

		if (tag === "dc-import") {
			const props = {};
			for (const { name, value } of [...child.attributes]) {
				if (name !== "name" && !HINT.test(name)) props[name] = fill(value, scopes);
			}
			child.replaceWith(await render(child.getAttribute("name"), props));
			continue;
		}

		if (tag === "sc-for") {
			const list = sole(child.getAttribute("list"), scopes) ?? [];
			const as = child.getAttribute("as");
			const out = document.createDocumentFragment();
			for (const item of list) {
				const one = document.createDocumentFragment();
				for (const inner of [...child.childNodes]) one.append(inner.cloneNode(true));
				await walk(one, [...scopes, { [as]: item }]);
				out.append(one);
			}
			child.replaceWith(out);
			continue;
		}

		if (tag === "sc-if") {
			if (sole(child.getAttribute("value"), scopes)) {
				const kept = document.createDocumentFragment();
				for (const inner of [...child.childNodes]) kept.append(inner);
				await walk(kept, scopes);
				child.replaceWith(kept);
			} else {
				child.remove();
			}
			continue;
		}

		for (const { name, value } of [...child.attributes]) {
			if (HINT.test(name) || HANDLER.test(name)) {
				// A hint is the design tool's, and onClick/onChange are its
				// React-shaped props: neither is an HTML attribute, and
				// \`onchange="(e) => …"\` in the output would be a third thing.
				child.removeAttribute(name);
			} else if (BOOLEAN.has(name)) {
				// React drops a false boolean; HTML treats checked="" as
				// checked, which would tick every box on the page.
				if (sole(value, scopes)) child.setAttribute(name, "");
				else child.removeAttribute(name);
			} else if (value.includes("{{")) {
				child.setAttribute(name, fill(value, scopes));
			}
		}
		// React carries a textarea's value in a prop; HTML carries it in the
		// element's text.
		if (tag === "textarea" && child.hasAttribute("value")) {
			child.textContent = child.getAttribute("value");
			child.removeAttribute("value");
		}
		await walk(child, scopes);
	}
}

window.drawMock = async (name) => {
	document.body.replaceChildren(await render(name, {}));
};
`;

/** Every screen's board, from the design tool's own canvas file. */
async function boards() {
	const canvas = JSON.parse(await readFile(join(SOURCE, "canvas.json"), "utf8"));
	return canvas.boards;
}

/**
 * Every source file. `Sidebar` and `Topbar` are shared parts drawn inside
 * the screens that import them, so they have no picture of their own and
 * are not in the default set — name one to draw it anyway.
 */
async function screenNames() {
	const files = await readdir(SOURCE);
	return files.filter((f) => f.endsWith(".dc.html")).map((f) => basename(f, ".dc.html"));
}

async function pictured() {
	const files = await readdir(SCREENS);
	return files.filter((f) => f.endsWith(".png")).map((f) => basename(f, ".png"));
}

async function main() {
	const wanted = process.argv.slice(2).filter((a) => !a.startsWith("--"));
	const all = await screenNames();
	const names = wanted.length ? wanted : await pictured();
	for (const name of names) {
		if (!all.includes(name)) {
			console.error(`No such screen: ${name}. One of: ${all.join(", ")}`);
			process.exit(1);
		}
	}

	const sizes = await boards();
	const browser = await chromium.launch();
	const context = await browser.newContext({ deviceScaleFactor: 1 });
	await context.route("**/*", async (route) => {
		const url = new URL(route.request().url());
		if (url.hostname !== "mock.local") return route.continue(); // the fonts
		if (url.pathname === "/support.js") {
			return route.fulfill({ contentType: TYPES[".js"], body: SUPPORT });
		}
		try {
			const body = await readFile(join(SOURCE, basename(url.pathname)));
			return route.fulfill({ contentType: TYPES[extname(url.pathname)] ?? "text/plain", body });
		} catch {
			return route.fulfill({ status: 404, body: "" });
		}
	});

	for (const name of names) {
		const board = sizes[`${name}.dc.html`] ?? { w: 1440, h: 1000 };
		const page = await context.newPage();
		const problems = [];
		page.on("pageerror", (e) => problems.push(e.message));
		await page.setViewportSize({ width: board.w, height: board.h });
		await page.goto(`http://mock.local/${name}.dc.html`, { waitUntil: "load" });
		await page.evaluate(`drawMock(${JSON.stringify(name)})`);
		await page.evaluate(() => document.fonts.ready);
		await page.waitForTimeout(250);
		if (problems.length) {
			console.error(`${name}: ${problems.join("; ")}`);
			await browser.close();
			process.exit(1);
		}
		const shot = await page.screenshot({ fullPage: true });
		await writeFile(join(SCREENS, `${name}.png`), shot);
		console.log(`${name.padEnd(13)} ${board.w}×${board.h}`);
		await page.close();
	}
	await browser.close();
}

await main();
