/**
 * The project form's values on their way to the API, and a failed save's
 * 422 on its way back to the inputs.
 */

import type { ApiContract, ApiProjectKind } from "@/shared/api";
import { apiFieldErrors } from "@/shared/api";
import type { Contract, ContractFrameErrors, TermFieldErrors } from "../model";
import { contractFieldErrors, contractFromForm, termFromForm, toApiContract } from "../model";
import type { ProjectFormValues } from "./ProjectForm";

/**
 * The `kind` and `contract` part of a create/update body.
 *
 * `contract` is present only for a day job that is describing one — the
 * API refuses a contract on any other kind (409), keeps what is stored
 * when the key is absent, and clears it with the kind when a PUT moves a
 * day job elsewhere. On a day job the terms are the existing contract's,
 * carried unchanged (they are edited only in the history panel), or the
 * form's one first term when there is no contract yet and the form is
 * adding one; the region, opening balance and end date are the form's
 * either way. A day job left without a contract sends `kind` alone.
 */
export function projectWriteFromForm(
	values: ProjectFormValues,
	existingContract: Contract | undefined,
): { kind: ApiProjectKind; contract?: ApiContract } {
	if (values.kind !== "day_job") return { kind: values.kind };
	if (!existingContract && !values.addContract) return { kind: "day_job" };
	const terms = existingContract ? existingContract.terms : [termFromForm(values.term)];
	return { kind: "day_job", contract: toApiContract(contractFromForm(values.contract, terms)) };
}

export interface ProjectFormErrors {
	name?: string;
	description?: string;
	color?: string;
	weeklyGoal?: string;
	goalType?: string;
	category?: string;
	githubRepo?: string;
	autostartRepos?: string;
	kind?: string;
	term: TermFieldErrors;
	contract: ContractFrameErrors;
	/** Messages with no input to sit beside. */
	general: string[];
}

export function emptyProjectFormErrors(): ProjectFormErrors {
	return { term: {}, contract: {}, general: [] };
}

export function hasProjectFormErrors(errors: ProjectFormErrors): boolean {
	const { term, contract, general, ...flat } = errors;
	return (
		general.length > 0 ||
		Object.keys(term).length > 0 ||
		Object.keys(contract).length > 0 ||
		Object.values(flat).some((v) => v !== undefined)
	);
}

const TOP_LEVEL: Record<string, keyof Omit<ProjectFormErrors, "term" | "contract" | "general">> = {
	name: "name",
	description: "description",
	color: "color",
	weekly_goal: "weeklyGoal",
	goal_type: "goalType",
	category: "category",
	github_repo: "githubRepo",
	autostart_repos: "autostartRepos",
	kind: "kind",
};

/**
 * A failed save's 422, sorted into the form's inputs. `fields[].path` is
 * the request's — `name`, `contract.holiday_country`,
 * `contract.terms.0.percentage` — and the form edits at most the first
 * term, so only that term's errors are pinned; anything else about the
 * contract reads as a general message. Empty for any other error (the
 * host toasts those).
 */
export function projectFormFieldErrors(err: unknown): ProjectFormErrors {
	const out = emptyProjectFormErrors();
	const fields = apiFieldErrors(err);
	const contractPaths: Record<string, string> = {};
	for (const [path, message] of Object.entries(fields)) {
		if (path === "contract" || path.startsWith("contract.")) {
			contractPaths[path] = message;
			continue;
		}
		const key = TOP_LEVEL[path.split(".")[0]];
		if (key) out[key] = message;
		else out.general.push(path ? `${path}: ${message}` : message);
	}
	const contract = contractFieldErrors(contractPaths, "contract", 0);
	out.term = contract.term;
	out.contract = contract.frame;
	out.general.push(...contract.general);
	return out;
}
