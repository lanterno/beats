/**
 * The house idioms the insights pages share (docs/project-page-mockup.html),
 * as the project page builds them in `pages/project-details/styles.ts`: the
 * small-caps label, the quiet sub, the link, the round nav button, the
 * segmented control, the chip on the sky. Restated here rather than imported
 * across pages; they are the same strings.
 */

/** `.lbl` — 10.5 px, bold, letter-spaced, muted. */
export const LABEL =
	"font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";

/** `.sec-h .sub` — the heading's quiet second half. */
export const SUB =
	"font-body font-medium tracking-normal normal-case text-[12.5px] text-muted-foreground ml-2";

/** A panel's quiet meta line, right of its label. */
export const META = "text-xs font-medium text-muted-foreground";

/** `.linkish` — a small bold link in the accent's ink. */
export const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** `.nav button` — the ‹ › round buttons, inside a panel. */
export const NAV_BUTTON =
	"grid place-items-center w-7 h-7 rounded-full bg-secondary text-foreground hover:bg-sidebar-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** `.hdr .chip` — a pill on the bare sky: the panel with ink on it. */
export const SKY_CHIP =
	"shrink-0 whitespace-nowrap text-[11px] font-bold px-2.5 py-1 rounded-full bg-card text-foreground shadow-soft hover:text-accent-ink transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** `.hdr .gear` — a round button on the bare sky. */
export const SKY_ROUND =
	"grid place-items-center w-8 h-8 rounded-full bg-card text-foreground shadow-soft hover:text-accent-ink transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** `.seg` — the pill group; the pressed option is the accent. */
export const SEG = "inline-flex flex-wrap gap-1 p-1 rounded-full bg-secondary";

export const SEG_BUTTON =
	"px-2 sm:px-2.5 py-1 rounded-full text-xs font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

export const SEG_ON = "bg-accent text-accent-foreground";

export const SEG_OFF = "text-muted-foreground hover:text-foreground";

/** `.chip` — a small pill on the wash. */
export const CHIP =
	"inline-flex items-center gap-1 text-xs font-bold px-2.5 py-0.5 rounded-full bg-secondary text-foreground whitespace-nowrap";

/** A row in a list of bars: the wash on hover, the heavier wash when chosen. */
export const ROW =
	"rounded-xl transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** A panel's footnote under its content, over the hairline. */
export const FOOTNOTE = "pt-2.5 border-t border-border text-xs font-medium text-muted-foreground";

/** A button on the bare sky: the sky chip at button size. */
export const SKY_BUTTON =
	"inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-bold px-3.5 py-1.5 rounded-full bg-card text-foreground shadow-soft hover:text-accent-ink transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/**
 * The sparklines' area: leaf at a low alpha, fading to nothing. Inline
 * styles, because `var()` does not resolve in a presentation attribute.
 */
export const AREA_TOP = { stopColor: "hsl(var(--success))", stopOpacity: 0.24 };
export const AREA_BOTTOM = { stopColor: "hsl(var(--success))", stopOpacity: 0.02 };

/** The score levels a sparkline's faint grid rules sit at. */
export const SPARK_GRID = [0.25, 0.5, 0.75];
