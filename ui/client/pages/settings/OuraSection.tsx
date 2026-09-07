import { CircleDot } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { describeError, post } from "@/shared/api";
import { Button } from "@/shared/ui";
import { IntegrationSection } from "./IntegrationSection";
import { useIntegration } from "./useIntegration";

export function OuraSection() {
	const oura = useIntegration("oura", "Oura");
	const [token, setToken] = useState("");
	const [connecting, setConnecting] = useState(false);

	const handleConnect = async () => {
		if (!token.trim()) return;
		setConnecting(true);
		try {
			await post("/api/oura/connect", { access_token: token.trim() });
			setToken("");
			toast.success("Oura connected");
			await oura.refresh();
		} catch (err) {
			toast.error(describeError(err, "Invalid Oura token — check and try again"));
		} finally {
			setConnecting(false);
		}
	};

	return (
		<IntegrationSection
			icon={CircleDot}
			title="Oura"
			description={
				<>
					Connect your Oura Ring to sync sleep, readiness, and HRV data. Get a personal access token
					from{" "}
					<a
						href="https://cloud.ouraring.com/personal-access-tokens"
						target="_blank"
						rel="noopener noreferrer"
						className="text-accent hover:underline"
					>
						cloud.ouraring.com
					</a>
					.
				</>
			}
			connected={oura.connected}
			onDisconnect={oura.disconnect}
			disconnecting={oura.isDisconnecting}
		>
			<div className="flex gap-2">
				<label className="sr-only" htmlFor="oura-token">
					Oura personal access token
				</label>
				<input
					id="oura-token"
					type="password"
					value={token}
					onChange={(e) => setToken(e.target.value)}
					placeholder="Oura personal access token"
					className="flex-1 px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/20 text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-accent"
				/>
				<Button
					size="sm"
					className="text-xs"
					onClick={handleConnect}
					disabled={connecting || !token.trim()}
				>
					{connecting ? "Connecting…" : "Connect"}
				</Button>
			</div>
		</IntegrationSection>
	);
}
