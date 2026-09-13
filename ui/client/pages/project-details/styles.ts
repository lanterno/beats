/**
 * The mockup's shared idioms (docs/project-page-mockup.html), once: the
 * small-caps label, a section heading with its sub, the pill, the tints.
 * Every panel on the page reads from here so the type stays one voice.
 */

import type { LedgerNoteKind } from "@/entities/project";

/** `.lbl` — 10.5 px, bold, letter-spaced, muted. */
export const LABEL =
	"font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";

/** `.sec-h .sub` — the heading's quiet second half. */
export const SUB =
	"font-body font-medium tracking-normal normal-case text-[12.5px] text-muted-foreground ml-2";

/** `.linkish` — a small bold link in the accent's ink. */
export const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** `.nav button` — the ‹ › round buttons. */
export const NAV_BUTTON =
	"grid place-items-center w-7 h-7 rounded-full bg-secondary text-foreground hover:bg-sidebar-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** `.tint` — a small pill for a day off, by why. */
export const TINT: Record<LedgerNoteKind, string> = {
	vacation: "bg-tint-vacation text-tint-vacation-ink",
	sick: "bg-tint-sick text-tint-sick-ink",
	holiday: "bg-tint-holiday text-tint-holiday-ink",
	other: "bg-tint-other text-tint-other-ink",
};

export const TINT_PILL =
	"inline-flex items-center gap-1 text-[11.5px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap";

/** The bar's colour in a ledger's day cells, by the day's note. */
export const CELL_TINT: Record<LedgerNoteKind, string> = {
	vacation: "bg-tint-vacation-ink",
	sick: "bg-destructive",
	holiday: "bg-accent",
	other: "bg-muted-foreground",
};

/**
 * Leaf for hours over, persimmon for hours owed, the muted ink for even, as
 * small text: the inks, since the fills are 3.3–3.5:1 on a panel by day.
 */
export const TONE = {
	over: "text-success-ink",
	owed: "text-destructive-ink",
	even: "text-muted-foreground",
} as const;

/** The same tones on the big balance figure, where the fills pass as large text. */
export const BIG_TONE = {
	over: "text-success",
	owed: "text-destructive",
	even: "text-muted-foreground",
} as const;

/** `.live` — the accent dot that breathes beside a running figure. */
export const LIVE_DOT =
	"inline-block w-[9px] h-[9px] rounded-full bg-accent shadow-[0_0_0_4px_hsl(var(--accent)/0.2)] animate-pulse";
