/**
 * What a command changed, read off the audit row's `before` and `after`:
 * one line per field whose value differs, "suspended: false → true", so
 * the audit says what happened without a reader comparing two objects. A
 * field one side lacks reads as "—" on that side.
 */

type Fields = Record<string, unknown> | null | undefined;

function shown(value: unknown): string {
	if (value === undefined || value === null) return "—";
	if (typeof value === "string") return value;
	return JSON.stringify(value);
}

export function changes(before: Fields, after: Fields): string[] {
	const keys = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]);
	const out: string[] = [];
	for (const key of [...keys].sort()) {
		const was = before?.[key];
		const now = after?.[key];
		if (JSON.stringify(was ?? null) === JSON.stringify(now ?? null)) continue;
		out.push(`${key}: ${shown(was)} → ${shown(now)}`);
	}
	return out;
}
