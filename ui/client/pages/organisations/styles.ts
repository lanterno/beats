/**
 * The organisation pages' idioms, in the settings page's voice
 * (`pages/settings/styles.ts`): a heading on the sky above each panel, the
 * small-caps label, the wash field, the hairline list, the round op button
 * and the small bold link. Pages do not import from one another, so the
 * constants are repeated here rather than reached across.
 */

/** A section's heading, on the sky above its panel. */
export const HEADING =
	"font-heading text-[15px] font-extrabold tracking-[-0.01em] text-foreground mb-3 flex items-center gap-2";

/** The heading's icon is decoration: muted, never the accent. */
export const HEADING_ICON = "w-4 h-4 text-muted-foreground";

/** `.lbl` — 10.5 px, bold, letter-spaced, muted. */
export const LABEL =
	"block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]";

/** A panel's lead paragraph. */
export const LEAD = "text-[12.5px] leading-normal text-muted-foreground";

/** A wash, no border, the accent's ring on focus; the destructive ring when invalid. */
export const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-medium placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent aria-invalid:ring-2 aria-invalid:ring-destructive/60 disabled:opacity-60";

/** A field's message, under it. */
export const ERROR = "mt-1 text-xs text-destructive-ink";

/** `.chip` — a pill on the wash. */
export const CHIP =
	"inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-xs font-bold text-foreground";

/** A list whose rows are separated by the hairline and nothing else. */
export const LIST = "divide-y divide-border";

/** A list row. */
export const ROW = "flex items-center gap-2 py-2 text-[12.5px]";

/** A row's round icon button that removes something. */
export const REMOVE =
	"grid place-items-center w-7 h-7 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-destructive-ink transition-colors shrink-0 disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** `.linkish` — a small bold link in the accent's ink. */
export const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** The ‹ › on the sky: the card is their ground, since a wash would vanish there. */
export const SKY_NAV =
	"grid place-items-center w-8 h-8 rounded-full text-foreground hover:bg-secondary transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** The page's title. */
export const TITLE = "font-heading text-2xl font-extrabold tracking-[-0.02em] text-foreground";
