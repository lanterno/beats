/**
 * ProjectGitHubBadge — header chip that surfaces the linked GitHub repo
 * (with an external link to github.com), or a "Connect GitHub" hint when
 * either the project has no `github_repo` set or the user isn't OAuth-
 * connected. Rendered next to the project title in the ProjectDetails
 * header. P4.4 of the project-management revamp.
 */

import { ExternalLink, GitBranch, Link2Off } from "lucide-react";
import { useGitHubStatus } from "@/entities/github";

interface ProjectGitHubBadgeProps {
	githubRepo: string | null | undefined;
	/** Opens the project settings drawer focused on the github_repo field. */
	onConfigure: () => void;
}

export function ProjectGitHubBadge({ githubRepo, onConfigure }: ProjectGitHubBadgeProps) {
	const { data: status } = useGitHubStatus();
	const repo = (githubRepo ?? "").trim();
	const hasRepo = repo.length > 0;
	const isConnected = !!status?.connected;

	if (hasRepo && isConnected) {
		return (
			<a
				href={`https://github.com/${repo}`}
				target="_blank"
				rel="noopener noreferrer"
				title={`Open ${repo} on GitHub`}
				className="hidden md:inline-flex items-center gap-1 text-[11px] text-muted-foreground border border-border/60 bg-secondary/30 rounded px-1.5 py-0.5 hover:text-foreground hover:border-muted-foreground/60 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 max-w-[220px]"
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
				onClick={onConfigure}
				title="Repo is set but GitHub isn't connected — commits won't sync until you connect"
				className="hidden md:inline-flex items-center gap-1 text-[11px] text-muted-foreground border border-dashed border-border/60 rounded px-1.5 py-0.5 hover:text-foreground hover:border-muted-foreground/60 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
			>
				<Link2Off className="w-3 h-3 shrink-0" aria-hidden="true" />
				Connect GitHub
			</button>
		);
	}

	return (
		<button
			type="button"
			onClick={onConfigure}
			title="Link a GitHub repo to surface commit activity on this project"
			className="hidden md:inline-flex items-center gap-1 text-[11px] text-muted-foreground/70 border border-dashed border-border/50 rounded px-1.5 py-0.5 hover:text-foreground hover:border-muted-foreground/60 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
		>
			<GitBranch className="w-3 h-3 shrink-0" aria-hidden="true" />
			Link a repo
		</button>
	);
}
