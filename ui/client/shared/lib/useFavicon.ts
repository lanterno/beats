/**
 * Favicon Timer Indicator Hook
 * When the timer is running, replaces the browser favicon with the day ring
 * drawn in the running project's colour. Restores the default favicon when
 * the timer stops.
 */
import { useEffect, useRef } from "react";

const DEFAULT_FAVICON = "/favicon.svg";
const SIZE = 32;

/** The day ring from shared/brand/favicon.svg, its arc and sun in [color]. */
function createTimerFavicon(color: string): string {
	const canvas = document.createElement("canvas");
	canvas.width = SIZE;
	canvas.height = SIZE;
	const ctx = canvas.getContext("2d");
	if (!ctx) return DEFAULT_FAVICON;

	const c = SIZE / 2;
	const r = 11.5;
	// Twelve o'clock, round two thirds of the day to eight.
	const from = -Math.PI / 2;
	const to = from + (Math.PI * 4) / 3;

	// No tile, like the favicon: the tab strip shows through. The track is a
	// slate at half strength, which reads on a light strip and a dark one.
	ctx.lineWidth = 4;
	ctx.lineCap = "round";
	ctx.beginPath();
	ctx.arc(c, c, r, 0, Math.PI * 2);
	ctx.strokeStyle = "rgb(124 147 168 / 0.45)";
	ctx.stroke();

	ctx.beginPath();
	ctx.arc(c, c, r, from, to);
	ctx.strokeStyle = color;
	ctx.stroke();

	ctx.beginPath();
	ctx.arc(c + r * Math.cos(to), c + r * Math.sin(to), 4.4, 0, Math.PI * 2);
	ctx.fillStyle = color;
	ctx.fill();

	return canvas.toDataURL("image/png");
}

function getOrCreateFaviconLink(): HTMLLinkElement {
	let link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
	if (!link) {
		link = document.createElement("link");
		link.rel = "icon";
		document.head.appendChild(link);
	}
	return link;
}

export function useFavicon(isRunning: boolean, projectColor: string | undefined) {
	const originalHref = useRef<string | null>(null);

	useEffect(() => {
		const link = getOrCreateFaviconLink();

		if (isRunning && projectColor) {
			// Save original on first activation
			if (originalHref.current === null) {
				originalHref.current = link.href || DEFAULT_FAVICON;
			}
			link.type = "image/png";
			link.href = createTimerFavicon(projectColor);
		} else if (originalHref.current !== null) {
			// Restore original
			link.href = originalHref.current;
			link.type = originalHref.current.endsWith(".svg") ? "image/svg+xml" : "image/png";
			originalHref.current = null;
		}
	}, [isRunning, projectColor]);
}
