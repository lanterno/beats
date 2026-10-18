/**
 * A billing budget, read off the API's figures (docs/billing.md, phase 1b).
 * The SPA never prices or adds anything here: spent, left, the state and
 * the projection are the API's, worked out as of today without a running
 * timer. The one thing worked out in the browser is the clock against the
 * instants the API sent for a running timer — `nearAt`, `overAt` — so a
 * crossing shows when it happens, not at the next read.
 */

import { formatDateShort, formatMoney, hoursText, parseIsoDate, parseUtcIso } from "@/shared/lib";
import type { BillingBudgetState, BillingBudgetStatus } from "./types";

/** What a budget says, sentence first. */
export interface BillingBudgetWords {
	/** "34 h of 40 h this month · 6 h left. At this pace it runs out around Oct 24." */
	sentence: string;
	/** A money budget's hours with no rate, which no figure counts. */
	unpriced?: string;
	/** What a running timer does to it, against the clock. */
	running?: string;
	/** The Clients page's note while it is near or used up, naming the budget. */
	note?: string;
}

function passed(instant: string | undefined, now: number): instant is string {
	return instant !== undefined && parseUtcIso(instant).getTime() <= now;
}

/**
 * The state to draw: the API's, lifted once the running timer's instant for
 * the next threshold has passed. Only ever lifted, since an instant is sent
 * only for a threshold not yet crossed.
 */
export function billingBudgetState(status: BillingBudgetStatus, now: number): BillingBudgetState {
	const running = status.running;
	if (!running) return status.state;
	if (passed(running.overAt, now)) return "used_up";
	if (passed(running.nearAt, now) && status.state === "under") return "near";
	return status.state;
}

/** "13:40", in the browser's zone. Whole minutes: the instant is "around". */
function clock(instant: string): string {
	const d = parseUtcIso(instant);
	return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** "Sep 1", or "Sep 1, 2025" outside `year`. */
function day(iso: string, year: number): string {
	const d = parseIsoDate(iso);
	if (!d) return iso;
	return d.getFullYear() === year
		? formatDateShort(d)
		: `${formatDateShort(d)}, ${d.getFullYear()}`;
}

/** "October", for the month a 'YYYY-MM-DD' is in. */
function monthName(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? d.toLocaleDateString("en-US", { month: "long" }) : iso;
}

/**
 * A budget in words, in the API's figures: how much of it is spent and
 * left this month or since its start, the projection when the API makes
 * one, a money budget's hours with no rate, what a running timer does to
 * it by `now`, and the note the Clients page lists while it is near or
 * used up.
 */
export function describeBillingBudget(
	status: BillingBudgetStatus,
	now: number,
): BillingBudgetWords {
	const year = parseIsoDate(status.through ?? status.first)?.getFullYear() ?? 0;
	const figure = (hours: number, minor: number) =>
		status.unit === "hours"
			? hoursText(hours)
			: formatMoney(minor, status.currency, status.minorUnits);
	const limit = figure(status.limitHours ?? 0, status.limitMinor ?? 0);

	if (status.upcoming) {
		return { sentence: `Starts ${day(status.first, year)}: ${limit} in total.` };
	}

	const remaining =
		status.unit === "hours" ? (status.remainingHours ?? 0) : (status.remainingMinor ?? 0);
	const left = figure(Math.abs(status.remainingHours ?? 0), Math.abs(status.remainingMinor ?? 0));
	const when = status.period === "monthly" ? "this month" : `since ${day(status.first, year)}`;
	const spent = `${figure(status.billableHours, status.amountMinor)} of ${limit} ${when}`;

	let sentence: string;
	if (status.state === "used_up") {
		sentence = remaining < 0 ? `${spent}: ${left} over.` : `${spent}: used up.`;
	} else {
		sentence = `${spent} · ${left} left.`;
		if (status.runsOutOn) {
			sentence += ` At this pace it runs out around ${day(status.runsOutOn, year)}.`;
		}
	}

	const words: BillingBudgetWords = { sentence };
	if (status.unit === "money" && status.unpricedHours > 0) {
		words.unpriced = `Plus ${hoursText(status.unpricedHours)} with no rate yet.`;
	}

	const running = status.running;
	if (running) {
		if (status.unit === "money" && !running.priced) {
			words.running = "A timer is running on hours with no rate; they count once a rate is set.";
		} else if (passed(running.overAt, now)) {
			words.running = `The running timer used it up around ${clock(running.overAt)}.`;
		} else if (running.overAt) {
			words.running = `A timer is running: it uses the last ${left} around ${clock(running.overAt)}.`;
		} else {
			words.running = "A timer is running; it counts once stopped.";
		}
	}

	const shown = billingBudgetState(status, now);
	const whose = `${status.name}'s budget`;
	if (shown === "used_up") {
		if (status.state !== "used_up" && running?.overAt) {
			words.note = `${whose} was used up around ${clock(running.overAt)} by the running timer.`;
		} else {
			words.note = remaining < 0 ? `${whose} is used up: ${left} over.` : `${whose} is used up.`;
		}
	} else if (shown === "near") {
		if (running?.overAt) {
			words.note = `${whose} runs out around ${clock(running.overAt)} if the timer keeps going.`;
		} else {
			const of = status.period === "monthly" ? ` for ${monthName(status.first)}` : "";
			words.note = `${whose}${of} is ${status.percentUsed}% used: ${left} left.`;
		}
	}
	return words;
}
