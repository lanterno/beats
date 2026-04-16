/**
 * Subsequence fuzzy matcher used by the command palette.
 *
 * `score(query, target)` returns a number in [0, 1]:
 *   - 0     when query's characters do not appear in target as an in-order subsequence
 *   - ~1    when every character matches at the very start of target
 *   - in between, higher when matches cluster together and hit word boundaries
 *
 * Case-insensitive. Empty query returns 1 (everything passes).
 */

export function score(query: string, target: string): number {
	if (!query) return 1;
	const q = query.toLowerCase();
	const t = target.toLowerCase();

	let qi = 0;
	let previousIndex = -1;
	let hits = 0;
	let clusterBonus = 0;
	let boundaryBonus = 0;

	for (let ti = 0; ti < t.length && qi < q.length; ti++) {
		if (t[ti] !== q[qi]) continue;
		hits += 1;
		if (previousIndex === ti - 1) clusterBonus += 1;
		if (ti === 0 || !/[a-z0-9]/i.test(t[ti - 1])) boundaryBonus += 1;
		previousIndex = ti;
		qi += 1;
	}

	if (qi < q.length) return 0;

	const coverage = hits / q.length;
	const density = hits / Math.max(1, t.length);
	const bonus = (clusterBonus + boundaryBonus) / (2 * q.length);

	// Weighted blend clamped into [0, 1].
	const raw = 0.55 * coverage + 0.2 * density + 0.25 * bonus;
	return Math.max(0, Math.min(1, raw));
}

export interface Scored<T> {
	item: T;
	score: number;
}

/**
 * Return `items` filtered to those that match `query`, sorted by descending score.
 * `getText` extracts the text to match against. `recencyBoost` is added to each
 * item's score (pre-clamp) before sorting — used to float recently-used actions.
 */
export function fuzzyRank<T>(
	items: T[],
	query: string,
	getText: (item: T) => string,
	recencyBoost: (item: T) => number = () => 0,
): Scored<T>[] {
	const results: Scored<T>[] = [];
	for (const item of items) {
		const base = score(query, getText(item));
		if (base === 0 && query) continue;
		results.push({ item, score: base + recencyBoost(item) });
	}
	results.sort((a, b) => b.score - a.score);
	return results;
}
