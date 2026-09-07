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
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Calendar className="w-4 h-4 text-accent" />
				Google Calendar
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Connect Google Calendar to see events alongside your tracked sessions. Read-only access —
					Beats never modifies your calendar.
				</p>
				{status?.connected ? (
					<div className="flex items-center gap-3">
						<span className="text-xs text-accent font-medium">Connected</span>
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
						Connect Google Calendar
					</button>
				)}
			</div>
		</section>
	);
}
