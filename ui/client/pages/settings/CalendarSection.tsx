import { Calendar } from "lucide-react";
import { toast } from "sonner";
import {
	fetchCalendarAuthUrl,
	useCalendarStatus,
	useConnectCalendar,
	useDisconnectCalendar,
} from "@/entities/calendar";
import { describeError } from "@/shared/api";
import { useOAuthCallback } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { CHIP, CONNECTED_DOT, DANGER_HOVER, HEADING, HEADING_ICON, LEAD } from "./styles";

export function CalendarSection() {
	const { data: status } = useCalendarStatus();
	const connectMutation = useConnectCalendar();
	const disconnectMutation = useDisconnectCalendar();
	const connectCalendar = connectMutation.mutate;

	useOAuthCallback(
		"calendar",
		connectCalendar,
		() => toast.success("Google Calendar connected"),
		() => toast.error("Failed to connect calendar"),
	);

	const handleConnect = async () => {
		try {
			const url = await fetchCalendarAuthUrl();
			window.location.href = url;
		} catch {
			toast.error("Failed to get auth URL — check Google OAuth credentials");
		}
	};

	const handleDisconnect = () => {
		disconnectMutation.mutate(undefined, {
			onSuccess: () => toast.success("Calendar disconnected"),
			onError: (err) => toast.error(describeError(err, "Failed to disconnect")),
		});
	};

	return (
		<section className="mb-8">
			<h2 className={HEADING}>
				<Calendar className={HEADING_ICON} />
				Google Calendar
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>
					Connect Google Calendar to see events alongside your tracked sessions. Read-only access —
					Beats never modifies your calendar.
				</p>
				{status?.connected ? (
					<div className="flex flex-wrap items-center gap-3">
						<span className={CHIP}>
							<span className={CONNECTED_DOT} />
							Connected
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
						Connect Google Calendar
					</Button>
				)}
			</Panel>
		</section>
	);
}
