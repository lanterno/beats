import { GitBranch } from "lucide-react";
import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { toast } from "sonner";
import {
	fetchGitHubAuthUrl,
	useConnectGitHub,
	useDisconnectGitHub,
	useGitHubStatus,
} from "@/entities/github";
import { describeError } from "@/shared/api";
import { useOAuthCallback } from "@/shared/lib";

export function GitHubSection() {
	const { data: status } = useGitHubStatus();
	const connectMutation = useConnectGitHub();
	const disconnectMutation = useDisconnectGitHub();
	const connectGitHub = connectMutation.mutate;
	// FF.14: when arriving at /settings#github (the path ProjectGitHubBadge's
	// "Connect GitHub" CTA dispatches to), scroll this section into view +
	// nudge focus to the connect button so the precondition closes the loop.
	const sectionRef = useRef<HTMLElement | null>(null);
	const location = useLocation();
	useEffect(() => {
		if (location.hash !== "#github" || !sectionRef.current) return;
		// rAF defers until after layout so the scroll lands on the right
		// element (some sections above might still be hydrating).
		const id = requestAnimationFrame(() => {
			sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
		});
		return () => cancelAnimationFrame(id);
	}, [location.hash]);

	useOAuthCallback(
		"github",
		connectGitHub,
		() => toast.success("GitHub connected"),
		() => toast.error("Failed to connect GitHub"),
	);

	const handleConnect = async () => {
		try {
			const url = await fetchGitHubAuthUrl();
			window.location.href = url;
		} catch {
			toast.error("Failed to get auth URL — check GitHub OAuth credentials");
		}
	};

	const handleDisconnect = () => {
		disconnectMutation.mutate(undefined, {
			onSuccess: () => toast.success("GitHub disconnected"),
			onError: (err) => toast.error(describeError(err, "Failed to disconnect")),
		});
	};

	return (
		<section ref={sectionRef} id="github" className="mb-8 scroll-mt-6">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<GitBranch className="w-4 h-4 text-accent" />
				GitHub
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Connect GitHub to see commit activity alongside your tracked sessions. Link a repo to a
					project in its settings to enable correlation.
				</p>
				{status?.connected ? (
					<div className="flex items-center gap-3">
						<span className="text-xs text-accent font-medium">
							Connected as {status.github_username}
						</span>
						<button
							type="button"
							onClick={handleDisconnect}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
						>
							Disconnect
						</button>
					</div>
				) : (
					<button
						type="button"
						onClick={handleConnect}
						className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
					>
						Connect GitHub
					</button>
				)}
			</div>
		</section>
	);
}
