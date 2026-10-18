/**
 * The public report, as `POST /api/public/reports` answers it and the
 * report link preview draws it (docs/billing.md, *Report links (phase 1c)*).
 *
 * Written by hand, field for field with `domain/report_links.py`'s
 * `PricedReport` and `HoursReport`, because this segment imports `zod` and
 * nothing else: the report page must not reach `@/shared/api`, whose client
 * attaches the session. A field the link does not show has no class on the
 * API's side; here the two shapes are told apart by `shows.amounts`, so a
 * priced body never reads as an hours-only one or the other way round.
 * Keys stay snake case, as they cross: the view reads them directly.
 */
import { z } from "zod";

const ReportDaySchema = z.object({
	day: z.string(), // YYYY-MM-DD, the local day its entries started on
	project_name: z.string(),
	hours: z.number(),
	// Only on a link that shows notes: its entries' notes, in start order.
	notes: z.array(z.string()).optional(),
});

const PricedLineSchema = z.object({
	project_name: z.string(),
	first: z.string(),
	last: z.string(),
	hours: z.number(),
	// null: no rate set, as on /api/billing/month.
	rate_minor: z.number().nullable(),
	amount_minor: z.number().nullable(),
});

const HoursLineSchema = z.object({
	project_name: z.string(),
	hours: z.number(),
});

const MonthFields = {
	month: z.string(), // YYYY-MM
	first: z.string(), // the month's days in the link
	last: z.string(),
	whole_month: z.boolean(),
	billable_hours: z.number(),
	days: z.array(ReportDaySchema),
};

const PricedMonthSchema = z.object({
	...MonthFields,
	amount_minor: z.number(),
	unpriced_hours: z.number(),
	lines: z.array(PricedLineSchema),
});

const HoursMonthSchema = z.object({
	...MonthFields,
	lines: z.array(HoursLineSchema),
});

const ReportMoneySchema = z.object({
	currency: z.string(),
	minor_units: z.number(),
	amount_minor: z.number(),
	unpriced_hours: z.number(),
});

const ReportFields = {
	client_name: z.string(),
	first: z.string(),
	last: z.string(),
	billable_hours: z.number(),
};

const PricedReportSchema = z.object({
	...ReportFields,
	shows: z.object({ amounts: z.literal(true), notes: z.boolean() }),
	money: ReportMoneySchema,
	months: z.array(PricedMonthSchema),
});

const HoursReportSchema = z.object({
	...ReportFields,
	shows: z.object({ amounts: z.literal(false), notes: z.boolean() }),
	months: z.array(HoursMonthSchema),
});

export const PublicReportSchema = z.union([PricedReportSchema, HoursReportSchema]);

export type PublicReport = z.infer<typeof PublicReportSchema>;
export type PricedReport = z.infer<typeof PricedReportSchema>;
export type HoursReport = z.infer<typeof HoursReportSchema>;
export type ReportMoney = z.infer<typeof ReportMoneySchema>;
export type PricedMonth = z.infer<typeof PricedMonthSchema>;
export type HoursMonth = z.infer<typeof HoursMonthSchema>;
export type ReportMonth = PricedMonth | HoursMonth;
export type PricedLine = z.infer<typeof PricedLineSchema>;
export type HoursLine = z.infer<typeof HoursLineSchema>;
export type ReportDay = z.infer<typeof ReportDaySchema>;
