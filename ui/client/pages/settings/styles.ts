/**
 * The settings page's idioms, once — the same voice as the project page's
 * (`pages/project-details/styles.ts`): a heading on the sky above each panel,
 * the small-caps label, the wash field, a state chip, the round op button.
 * Every section reads from here so thirteen files cannot drift apart again.
 */

/** A section's heading, on the sky above its panel. */
export const HEADING =
	"font-heading text-[15px] font-extrabold tracking-[-0.01em] text-foreground mb-3 flex items-center gap-2";

/** The heading's icon is decoration: muted, never the accent. */
export const HEADING_ICON = "w-4 h-4 text-muted-foreground";

/** `.lbl` — 10.5 px, bold, letter-spaced, muted. */
export const LABEL =
	"font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";

/** A panel's lead paragraph. */
export const LEAD = "text-[12.5px] leading-normal text-muted-foreground";

/** The mockup's `.dlg input`: a wash, no border, the accent's ring on focus. */
export const FIELD =
	"min-w-0 rounded-xl bg-secondary px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent";

/** `.chip` — a pill on the wash. */
export const CHIP =
	"inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-xs font-bold text-foreground";

/** Leaf, because connected is a state that means something. */
export const CONNECTED_DOT = "w-1.5 h-1.5 rounded-full bg-success shrink-0";

/** A light-wash pill that acts — lighter than `Button`, for a run of many. */
export const CHIP_BUTTON =
	"inline-flex items-center rounded-full bg-secondary px-3 py-1.5 text-xs font-bold text-foreground hover:bg-sidebar-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** A list whose rows are separated by the hairline and nothing else. */
export const LIST = "divide-y divide-border";

/** A list row. */
export const ROW = "flex items-center gap-2 py-2 text-[12.5px]";

/** A row's round icon button that removes something. */
export const REMOVE =
	"grid place-items-center w-7 h-7 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-destructive-ink transition-colors shrink-0 disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** A `Button` whose action takes something away: the ink turns on hover. */
export const DANGER_HOVER = "hover:text-destructive-ink";

/** `.linkish` — a small bold link in the accent's ink. */
export const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
