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
import { Button, Panel } from "@/shared/ui";
import { CHIP, CONNECTED_DOT, DANGER_HOVER, HEADING, HEADING_ICON, LEAD } from "./styles";

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
			<h2 className={HEADING}>
				<GitBranch className={HEADING_ICON} />
				GitHub
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>
					Connect GitHub to see commit activity alongside your tracked sessions. Link a repo to a
					project in its settings to enable correlation.
				</p>
				{status?.connected ? (
					<div className="flex flex-wrap items-center gap-3">
						<span className={CHIP}>
							<span className={CONNECTED_DOT} />
							Connected as {status.github_username}
						</span>
						<Button
							variant="secondary"
							size="sm"
							onClick={handleDisconnect}
							className={DANGER_HOVER}
						>
							Disconnect
						</Button>
					</div>
				) : (
					<Button variant="secondary" size="sm" onClick={handleConnect}>
						Connect GitHub
					</Button>
				)}
			</Panel>
		</section>
	);
}
