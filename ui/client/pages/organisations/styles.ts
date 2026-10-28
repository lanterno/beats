/**
 * The organisation pages' idioms, in the settings page's voice
 * (`pages/settings/styles.ts`): the small-caps label, the wash field, the
 * hairline list, the round op button and the small bold link — headings
 * live inside their panels now (`Section`). Pages do not import from one
 * another, so the constants are repeated here rather than reached across.
 */

/** A panel heading's icon is decoration: muted, never the accent. */
export const HEADING_ICON = "w-4 h-4 text-muted-foreground";

/** `.lbl` — 10.5 px, bold, letter-spaced, muted. */
export const LABEL =
	"block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]";

/** A panel's lead paragraph. */
export const LEAD = "text-[12.5px] leading-normal text-muted-foreground";

/** A wash, no border, the accent's ring on focus; the destructive ring when invalid. */
export const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-medium placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent aria-invalid:ring-2 aria-invalid:ring-destructive/60 disabled:opacity-60";

/** A compact select in a row: the wash, sized to its text, never the row's width. */
export const SELECT =
	"min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-1.5 text-xs font-bold focus:outline-hidden focus:ring-[3px] focus:ring-accent disabled:opacity-60";

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

/** A secondary button that destroys something: the warning on hover. */
export const DANGER_HOVER = "hover:text-destructive-ink";

/** `.linkish` — a small bold link in the accent's ink. */
export const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** The page's title. */
export const TITLE = "font-heading text-2xl font-extrabold tracking-[-0.02em] text-foreground";

/**
 * The page's container. Wide, because the sidebar already takes 18rem and a
 * single narrow column wastes the rest; the grids below use the width.
 */
/** `page-sheet`: under the sheet layout the stack is the page's one card (global.css). */
export const PAGE = "page-sheet max-w-6xl mx-auto px-4 sm:px-6 py-4 space-y-4 pb-24";

/**
 * `.pagebar` — a Panel strip at the top of a page: the mark, the title or
 * breadcrumb, the status chips, the tabs and the one primary action. The
 * sky is the least readable surface in the app, so nothing a page is read
 * by sits on it.
 */
export const PAGEBAR = "flex items-center gap-x-3 gap-y-2 flex-wrap";

/** `.pagebar h1` — smaller than a bare sky title, since it sits on the card. */
export const PAGE_TITLE =
	"font-heading text-[19px] font-extrabold tracking-[-0.02em] text-foreground";

/** `.crumbs` — the trail back, muted, with the current page in the ink. */
export const CRUMB =
	"text-[13px] text-muted-foreground hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** A heading inside its panel, above the hairline that separates it from the body. */
export const PANEL_HEADING =
	"font-heading text-[15.5px] font-extrabold tracking-[-0.01em] text-foreground flex items-center gap-2 min-w-0";

/** The ‹ › inside a page bar's card, where a wash reads (the Clients page's). */
export const MONTH_NAV =
	"grid place-items-center w-8 h-8 rounded-full text-foreground hover:bg-secondary transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** An absence's kind on its tint — the project page's idiom, repeated here. */
export const TINT: Record<"vacation" | "sick" | "holiday" | "other", string> = {
	vacation: "bg-tint-vacation text-tint-vacation-ink",
	sick: "bg-tint-sick text-tint-sick-ink",
	holiday: "bg-tint-holiday text-tint-holiday-ink",
	other: "bg-tint-other text-tint-other-ink",
};

export const TINT_PILL =
	"inline-flex items-center gap-1 text-[11.5px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap";
