import { Heart } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { describeError, get, post } from "@/shared/api";
import { useOAuthCallback } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { IntegrationSection } from "./IntegrationSection";
import { useIntegration } from "./useIntegration";

export function FitbitSection() {
	const fitbit = useIntegration("fitbit", "Fitbit");
	const [redirecting, setRedirecting] = useState(false);

	// Fitbit sends the browser back to /settings?fitbit=callback&code=… — without
	// this the redirect lands on a page that quietly does nothing with it.
	const exchangeCode = useCallback(
		(code: string, opts: { onSuccess: () => void; onError: () => void }) => {
			post(`/api/fitbit/connect?code=${encodeURIComponent(code)}`)
				.then(opts.onSuccess)
				.catch(opts.onError);
		},
		[],
	);

	useOAuthCallback(
		"fitbit",
		exchangeCode,
		() => {
			toast.success("Fitbit connected");
			void fitbit.refresh();
		},
		() => toast.error("Failed to connect Fitbit"),
	);

	const handleConnect = async () => {
		setRedirecting(true);
		try {
			const { url } = await get<{ url: string }>("/api/fitbit/auth-url");
			window.location.href = url;
		} catch (err) {
			toast.error(describeError(err, "Failed to get Fitbit auth URL"));
			setRedirecting(false);
		}
	};

	return (
		<IntegrationSection
			icon={Heart}
			title="Fitbit"
			description="Connect Fitbit to sync sleep, HRV, resting heart rate, and activity data for recovery-aware coaching."
			connected={fitbit.connected}
			connectedDetail={fitbit.details?.fitbit_user_id as string | undefined}
			onDisconnect={fitbit.disconnect}
			disconnecting={fitbit.isDisconnecting}
		>
			<Button size="sm" className="text-xs" onClick={handleConnect} disabled={redirecting}>
				{redirecting ? "Connecting…" : "Connect Fitbit"}
			</Button>
		</IntegrationSection>
	);
}
