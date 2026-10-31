/**
 * Chip — a state said in a word, on a wash in that word's tone. The word
 * is the state and the tone only agrees with it, so a
 * reader who cannot tell the tones apart loses nothing.
 *
 * The tones are the ink tokens, never the raw accent or the tints: `--*-ink`
 * is the tone that is legible as small text on a panel, and the `tint-*`
 * tokens mean an absence's kind (vacation, sick, holiday, other), which is a
 * different thing from a state being good or bad.
 */

import type { ReactNode } from "react";
import { cn } from "@/shared/lib";

export type ChipTone = "ok" | "warn" | "bad" | "wait";

const TONES: Record<ChipTone, string> = {
	ok: "bg-success/15 text-success-ink",
	warn: "bg-accent/20 text-accent-ink",
	bad: "bg-destructive/15 text-destructive-ink",
	wait: "bg-secondary text-muted-foreground",
};

export interface ChipProps {
	tone?: ChipTone;
	className?: string;
	children: ReactNode;
}

export function Chip({ tone = "wait", className, children }: ChipProps) {
	return (
		<span
			className={cn(
				"inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-heading text-[12px] font-bold whitespace-nowrap",
				TONES[tone],
				className,
			)}
		>
			{children}
		</span>
	);
}
