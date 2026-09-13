/**
 * ProjectGitHubBadge — header chip that surfaces the linked GitHub repo
 * (with an external link to github.com), or one of two CTAs:
 *
 * - "Connect GitHub" when the repo IS set but OAuth isn't connected. Routes
 *   to /settings (the canonical OAuth surface).
 * - "Link a repo" when no repo is set. Opens the project settings drawer
 *   focused on the github_repo field inside the Advanced disclosure.
 *
 * The two CTAs were a single onConfigure callback wired to focus the *name*
 * field — the FF.2 audit caught that "Connect GitHub" promised something the
 * drawer couldn't deliver. The badge now also suppresses the CTA
 * while the status query is still in flight, so a hard reload of a connected
 * project no longer flashes "Connect GitHub" before resolving to the link.
 */

import { ExternalLink, GitBranch, Link2Off } from "lucide-react";
import { useGitHubStatus } from "@/entities/github";

interface ProjectGitHubBadgeProps {
	githubRepo: string | null | undefined;
	/** Opens the project settings drawer focused on the github_repo field
	 *  (in the Advanced disclosure). */
	onConfigureRepo: () => void;
	/** Navigates to the canonical GitHub OAuth surface (Settings page). */
	onConnectGitHub: () => void;
}

export function ProjectGitHubBadge({
	githubRepo,
	onConfigureRepo,
	onConnectGitHub,
}: ProjectGitHubBadgeProps) {
	const { data: status, isPending } = useGitHubStatus();
	const repo = (githubRepo ?? "").trim();
	const hasRepo = repo.length > 0;
	const isConnected = !!status?.connected;

	// Suppress the "Connect GitHub" CTA while we don't yet know the
	// connection status for a project that has a repo set — otherwise the
	// badge flashes "Connect" on every hard reload for connected users.
	// `data === undefined` covers both initial fetch and refetch-after-error.
	if (hasRepo && status === undefined && isPending) {
		return (
			<span
				className="hidden md:inline-flex items-center gap-1.5 rounded-full bg-sidebar/50 px-[11px] py-[3px] text-xs font-bold text-muted-foreground max-w-[220px]"
				aria-hidden="true"
			>
				<GitBranch className="w-3 h-3 shrink-0" aria-hidden="true" />
				<span className="truncate">{repo}</span>
			</span>
		);
	}

	if (hasRepo && isConnected) {
		return (
			<a
				href={`https://github.com/${repo}`}
				target="_blank"
				rel="noopener noreferrer"
				title={`Open ${repo} on GitHub`}
				className="hidden md:inline-flex items-center gap-1.5 rounded-full bg-sidebar px-[11px] py-[3px] text-xs font-bold text-foreground hover:text-accent-ink transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring max-w-[220px]"
			>
				<GitBranch className="w-3 h-3 shrink-0" aria-hidden="true" />
				<span className="truncate">{repo}</span>
				<ExternalLink className="w-2.5 h-2.5 shrink-0 opacity-60" aria-hidden="true" />
			</a>
		);
	}

	if (hasRepo && !isConnected) {
		return (
			<button
				type="button"
				onClick={onConnectGitHub}
				title="Repo is set but GitHub isn't connected — commits won't sync until you connect"
				className="hidden md:inline-flex items-center gap-1.5 rounded-full bg-sidebar/60 px-[11px] py-[3px] text-xs font-bold text-foreground/80 hover:bg-sidebar hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
			>
				<Link2Off className="w-3 h-3 shrink-0" aria-hidden="true" />
				Connect GitHub
			</button>
		);
	}

	return (
		<button
			type="button"
			onClick={onConfigureRepo}
			title="Link a GitHub repo to surface commit activity on this project"
			className="hidden md:inline-flex items-center gap-1.5 rounded-full bg-sidebar/60 px-[11px] py-[3px] text-xs font-bold text-foreground/80 hover:bg-sidebar hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
		>
			<GitBranch className="w-3 h-3 shrink-0" aria-hidden="true" />
			Link a repo
		</button>
	);
}
