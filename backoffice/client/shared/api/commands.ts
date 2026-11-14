/**
 * The one path a mutation takes: POST /api/operator/commands/{name} with
 * `args` and, where the command demands it, the confirmation the operator
 * typed — the account's email, the organisation's name. The browser attaches
 * its own Origin header, which the server requires on every write; nothing
 * here can or should fake one.
 */

import { post } from "./client";
import type { CommandPreview } from "./schema";

/** What an inline command answers: the row the runner wrote. */
export interface AuditEntry {
	id: string;
	at: string;
	command: string;
	subject_kind: string;
	subject_id: string;
	before: Record<string, unknown>;
	after: Record<string, unknown>;
}

/**
 * What a windowed command answers instead: the job now waiting. Its audit
 * row is written when it runs, by the same runner.
 */
export interface QueuedJob {
	queued: true;
	job: Record<string, unknown>;
}

export type CommandResult = AuditEntry | QueuedJob;

export function runCommand(
	name: string,
	args: Record<string, unknown>,
	confirmation?: string,
): Promise<CommandResult> {
	return post<CommandResult>(`/api/operator/commands/${name}`, {
		args,
		confirmation: confirmation || null,
	});
}

/**
 * What the command would do, from the runner's own gates: the subject as it
 * stands, whether it will ask for the subject typed back, and when it would
 * run. It writes nothing — the review page reads it before anything is
 * typed, so a mistyped id or an already-queued window is answered first.
 */
export function previewCommand(
	name: string,
	args: Record<string, unknown>,
): Promise<CommandPreview> {
	return post<CommandPreview>(`/api/operator/commands/${name}/preview`, { args });
}
