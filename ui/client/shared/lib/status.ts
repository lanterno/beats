/**
 * The public status file (docs/status-page.md), as the page and the banner
 * read it. Pure: what the file means, and the sentence for each state. A
 * file that cannot be read is "unknown", and the page says the status could
 * not be loaded — never "all good".
 */

export type StatusState = "operational" | "degraded" | "outage" | "maintenance";

export interface StatusPost {
	at: string;
	state: StatusState;
	message: string;
	affected: string[];
}

export interface StatusDoc {
	state: StatusState;
	message: string;
	affected: string[];
	updated_at: string;
	posts: StatusPost[];
}

const STATES: ReadonlySet<string> = new Set(["operational", "degraded", "outage", "maintenance"]);

const isState = (value: unknown): value is StatusState =>
	typeof value === "string" && STATES.has(value);

const strings = (value: unknown): string[] =>
	Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];

/** The file, checked field by field; null for anything that is not one. */
export function parseStatus(raw: unknown): StatusDoc | null {
	if (!raw || typeof raw !== "object") return null;
	const r = raw as Record<string, unknown>;
	if (!isState(r.state) || typeof r.updated_at !== "string") return null;
	const posts = Array.isArray(r.posts)
		? r.posts.flatMap((p): StatusPost[] => {
				if (!p || typeof p !== "object") return [];
				const q = p as Record<string, unknown>;
				if (!isState(q.state) || typeof q.at !== "string") return [];
				return [
					{
						at: q.at,
						state: q.state,
						message: typeof q.message === "string" ? q.message : "",
						affected: strings(q.affected),
					},
				];
			})
		: [];
	return {
		state: r.state,
		message: typeof r.message === "string" ? r.message : "",
		affected: strings(r.affected),
		updated_at: r.updated_at,
		posts,
	};
}

/** The plain sentence the page and the banner lead with. */
export function statusSentence(doc: StatusDoc): string {
	const parts = doc.affected.length ? ` (${doc.affected.join(", ")})` : "";
	switch (doc.state) {
		case "operational":
			return "Everything is working.";
		case "degraded":
			return `Something is slower or flakier than it should be${parts}.`;
		case "outage":
			return `Something is down${parts}.`;
		case "maintenance":
			return `Planned maintenance is under way${parts}.`;
	}
}

/** The banner shows only when there is something to say. */
export const showsBanner = (doc: StatusDoc | null): boolean =>
	doc !== null && doc.state !== "operational";

/** One fetch of the file: a document, or null for anything that fails. */
export async function fetchStatus(
	url: string,
	fetcher: typeof fetch = fetch,
): Promise<StatusDoc | null> {
	try {
		const resp = await fetcher(url, { cache: "no-store" });
		if (!resp.ok) return null;
		return parseStatus(await resp.json());
	} catch {
		return null;
	}
}
