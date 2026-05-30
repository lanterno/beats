/**
 * Advanced project fields — category, GitHub repo, and autostart_repos.
 * Surface inside the ProjectForm behind a disclosure so the default form
 * stays tight; the Advanced disclosure is where these "previously
 * invisible" backend fields finally become editable from the UI.
 *
 * P1.2b of the project-management revamp.
 */

import { GitBranch, Plus, Trash2 } from "lucide-react";
import { useId, useMemo } from "react";

export interface AdvancedFieldsValues {
	category: string;
	githubRepo: string;
	autostartRepos: string[];
}

export interface AdvancedFieldsProps {
	values: AdvancedFieldsValues;
	onChange: (next: AdvancedFieldsValues) => void;
	/** Pre-existing category strings to seed the combobox. */
	categorySuggestions?: string[];
	/** Whether the user has GitHub OAuth connected — surfaces a hint if not. */
	githubConnected?: boolean;
}

// Loose owner/repo match: word chars, dots, hyphens, exactly one slash.
const GITHUB_REPO_RE = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;

/**
 * True iff the input is empty (no validation needed) OR matches owner/repo
 * shape. Empty is allowed because the field is optional.
 */
export function isValidGithubRepo(input: string): boolean {
	const trimmed = input.trim();
	if (trimmed === "") return true;
	return GITHUB_REPO_RE.test(trimmed);
}

const inputCls =
	"w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40";
const labelCls = "block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5";

export function AdvancedFields({
	values,
	onChange,
	categorySuggestions,
	githubConnected,
}: AdvancedFieldsProps) {
	const catListId = useId();
	const repoInvalid = !isValidGithubRepo(values.githubRepo);

	const suggestions = useMemo(
		() => [...new Set(categorySuggestions ?? [])].sort((a, b) => a.localeCompare(b)),
		[categorySuggestions],
	);

	const set = <K extends keyof AdvancedFieldsValues>(k: K, v: AdvancedFieldsValues[K]) =>
		onChange({ ...values, [k]: v });

	const setRepo = (i: number, v: string) => {
		const next = values.autostartRepos.slice();
		next[i] = v;
		set("autostartRepos", next);
	};

	const removeRepo = (i: number) => {
		const next = values.autostartRepos.slice();
		next.splice(i, 1);
		set("autostartRepos", next);
	};

	const addRepo = () => set("autostartRepos", [...values.autostartRepos, ""]);

	return (
		<div className="space-y-4">
			<div>
				<label htmlFor="project-form-category" className={labelCls}>
					Category
				</label>
				<input
					id="project-form-category"
					value={values.category}
					onChange={(e) => set("category", e.target.value)}
					list={catListId}
					placeholder="coding, design, writing…"
					className={inputCls}
				/>
				<datalist id={catListId}>
					{suggestions.map((s) => (
						<option key={s} value={s} />
					))}
				</datalist>
				<p className="text-[11px] text-muted-foreground/60 mt-1">
					Used by the daemon's flow-score category-fit matcher.
				</p>
			</div>

			<div>
				<label htmlFor="project-form-github-repo" className={labelCls}>
					GitHub repo
				</label>
				<div className="flex items-center gap-2">
					<GitBranch className="w-4 h-4 text-muted-foreground/70 shrink-0" aria-hidden="true" />
					<input
						id="project-form-github-repo"
						value={values.githubRepo}
						onChange={(e) => set("githubRepo", e.target.value)}
						placeholder="owner/repo"
						aria-invalid={repoInvalid}
						aria-describedby={
							repoInvalid
								? "project-form-github-repo-error"
								: githubConnected === false
									? "project-form-github-repo-hint"
									: undefined
						}
						className={`${inputCls} ${repoInvalid ? "border-destructive/50" : ""}`}
					/>
				</div>
				{repoInvalid && (
					<p
						id="project-form-github-repo-error"
						role="alert"
						className="text-[11px] text-destructive mt-1"
					>
						Use the <code>owner/repo</code> format (e.g. <code>lanterno/beats</code>).
					</p>
				)}
				{!repoInvalid && githubConnected === false && (
					<p
						id="project-form-github-repo-hint"
						className="text-[11px] text-muted-foreground/70 mt-1"
					>
						Connect GitHub in Settings to populate commit counts for this project.
					</p>
				)}
			</div>

			<div>
				<span id="project-form-autostart-label" className={labelCls}>
					Autostart paths
				</span>
				<p className="text-[11px] text-muted-foreground/60 mb-2">
					Local repo paths the daemon auto-starts a timer for.
				</p>
				<div className="space-y-1.5" role="group" aria-labelledby="project-form-autostart-label">
					{values.autostartRepos.map((repo, i) => (
						<div key={i} className="flex items-center gap-2">
							<input
								value={repo}
								onChange={(e) => setRepo(i, e.target.value)}
								placeholder="/Users/me/code/beats"
								aria-label={`Autostart path ${i + 1}`}
								className={`${inputCls} font-mono text-sm`}
							/>
							<button
								type="button"
								onClick={() => removeRepo(i)}
								aria-label={`Remove autostart path ${i + 1}`}
								className="p-2 rounded-md text-muted-foreground/60 hover:text-destructive hover:bg-secondary/40 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
							>
								<Trash2 className="w-4 h-4" />
							</button>
						</div>
					))}
					<button
						type="button"
						onClick={addRepo}
						className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
					>
						<Plus className="w-3.5 h-3.5" />
						{values.autostartRepos.length === 0 ? "Add a path" : "Add another"}
					</button>
				</div>
			</div>
		</div>
	);
}
