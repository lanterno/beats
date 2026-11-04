/**
 * The one path a mutation takes: POST /api/operator/commands/{name} with
 * `args` and, where the command demands it, the confirmation the operator
 * typed — the account's email, the organisation's name. The browser attaches
 * its own Origin header, which the server requires on every write; nothing
 * here can or should fake one.
 */

import { post } from "./client";

export interface AuditEntry {
	id: string;
	at: string;
	command: string;
	subject_kind: string;
	subject_id: string;
	before: Record<string, unknown>;
	after: Record<string, unknown>;
}

export function runCommand(
	name: string,
	args: Record<string, unknown>,
	confirmation?: string,
): Promise<AuditEntry> {
	return post<AuditEntry>(`/api/operator/commands/${name}`, {
		args,
		confirmation: confirmation || null,
	});
}
