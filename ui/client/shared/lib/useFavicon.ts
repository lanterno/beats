/**
 * Favicon Timer Indicator Hook
 * When the timer is running, replaces the browser favicon with a
 * canvas-generated icon showing a colored dot matching the project color.
 * Restores the default favicon when the timer stops.
 */
import { useEffect, useRef } from "react";

const DEFAULT_FAVICON = "/favicon.svg";
const SIZE = 32;

function createTimerFavicon(color: string): string {
	const canvas = document.createElement("canvas");
	canvas.width = SIZE;
	canvas.height = SIZE;
	const ctx = canvas.getContext("2d");
	if (!ctx) return DEFAULT_FAVICON;

	// Outer ring
	ctx.beginPath();
	ctx.arc(SIZE / 2, SIZE / 2, 13, 0, Math.PI * 2);
	ctx.strokeStyle = color;
	ctx.lineWidth = 2.5;
	ctx.stroke();

	// Inner filled dot
	ctx.beginPath();
	ctx.arc(SIZE / 2, SIZE / 2, 7, 0, Math.PI * 2);
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
