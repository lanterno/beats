/**
 * Focus Mode Component
 * Distraction-free overlay: large timer, project name, stop button.
 * Toggled via F key or button. Supports fullscreen.
 */

import { Maximize2, Minimize2, Square } from "lucide-react";
import { useCallback, useEffect } from "react";
import { cn, formatSecondsToTime } from "@/shared/lib";
import { AnimatedDigits } from "./animated-digits";

interface FocusModeProps {
	open: boolean;
	onClose: () => void;
	isRunning: boolean;
	totalSeconds: number;
	projectName: string | undefined;
	projectColor: string | undefined;
	onStop: () => void;
}

export function FocusMode({
	open,
	onClose,
	isRunning,
	totalSeconds,
	projectName,
	projectColor,
	onStop,
}: FocusModeProps) {
	const toggleFullscreen = useCallback(() => {
		if (document.fullscreenElement) {
			document.exitFullscreen();
		} else {
			document.documentElement.requestFullscreen();
		}
	}, []);

	// Close on Escape or F
	useEffect(() => {
		if (!open) return;
		function handleKey(e: KeyboardEvent) {
			if (e.key === "Escape" || e.key === "f" || e.key === "F") {
				e.preventDefault();
				onClose();
				if (document.fullscreenElement) {
					document.exitFullscreen();
				}
			}
		}
		window.addEventListener("keydown", handleKey);
		return () => window.removeEventListener("keydown", handleKey);
	}, [open, onClose]);

	// Exit focus mode if timer stops
	useEffect(() => {
		if (open && !isRunning) {
			onClose();
			if (document.fullscreenElement) {
				document.exitFullscreen();
			}
		}
	}, [open, isRunning, onClose]);

	if (!open) return null;

	return (
		<div
			className="fixed inset-0 z-[200] bg-background flex flex-col items-center justify-center"
			style={{
				backgroundImage:
					"radial-gradient(ellipse at 50% 40%, hsl(38 20% 12%) 0%, hsl(25 15% 6%) 70%)",
			}}
		>
			{/* Top controls */}
			<div className="absolute top-4 right-4 flex items-center gap-2">
				<button
					onClick={toggleFullscreen}
					className="p-2 rounded-md text-muted-foreground/40 hover:text-muted-foreground transition-colors"
					title="Toggle fullscreen"
				>
					{document.fullscreenElement ? (
						<Minimize2 className="w-5 h-5" />
					) : (
						<Maximize2 className="w-5 h-5" />
					)}
				</button>
				<button
					onClick={onClose}
					className="px-3 py-1.5 rounded-md text-xs text-muted-foreground/40 hover:text-muted-foreground transition-colors"
				>
					ESC
				</button>
			</div>

			{/* Project indicator */}
			{projectName && (
				<div className="flex items-center gap-3 mb-6">
					<div className="w-3 h-3 rounded-full" style={{ backgroundColor: projectColor }} />
					<span className="text-muted-foreground text-lg font-medium">{projectName}</span>
				</div>
			)}

			{/* Giant timer */}
			<AnimatedDigits
				value={formatSecondsToTime(totalSeconds)}
				className={cn(
					"font-mono font-semibold tabular-nums tracking-tight text-accent",
					"text-7xl sm:text-8xl md:text-9xl",
				)}
			/>

			{/* Pulse indicator */}
			<div className="mt-6 flex items-center gap-2">
				<span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
				<span className="text-muted-foreground/60 text-sm">Recording</span>
			</div>

			{/* Stop button */}
			<button
				onClick={onStop}
				className="mt-12 flex items-center gap-2.5 px-8 py-3 rounded-lg text-sm font-medium bg-destructive text-destructive-foreground hover:bg-destructive/85 transition-colors"
			>
				<Square className="w-4 h-4" />
				Stop
			</button>

			{/* Keyboard hint */}
			<p className="absolute bottom-6 text-muted-foreground/20 text-xs">
				Press{" "}
				<kbd className="px-1.5 py-0.5 rounded bg-secondary/30 text-muted-foreground/30">F</kbd> or{" "}
				<kbd className="px-1.5 py-0.5 rounded bg-secondary/30 text-muted-foreground/30">ESC</kbd> to
				exit
			</p>
		</div>
	);
}
