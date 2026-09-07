import { Heart } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { describeError, get } from "@/shared/api";
import { Button } from "@/shared/ui";
import { IntegrationSection } from "./IntegrationSection";
import { useIntegration } from "./useIntegration";

export function FitbitSection() {
	const fitbit = useIntegration("fitbit", "Fitbit");
	const [redirecting, setRedirecting] = useState(false);

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
