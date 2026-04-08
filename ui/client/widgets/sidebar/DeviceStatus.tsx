/**
 * Device Status Widget
 * Shows wall clock connection status in the sidebar.
 */
import { useQuery } from "@tanstack/react-query";
import { Battery, Wifi, WifiOff } from "lucide-react";
import { get } from "@/shared/api";

interface DeviceHeartbeat {
	battery_voltage: number | null;
	wifi_rssi: number | null;
	uptime_seconds: number | null;
	last_seen: string | null;
}

function useDeviceHeartbeat() {
	return useQuery({
		queryKey: ["device", "heartbeat"],
		queryFn: () => get<DeviceHeartbeat | null>("/api/device/heartbeat"),
		refetchInterval: 30_000,
	});
}

function formatTimeAgo(isoDate: string): string {
	const diff = Date.now() - new Date(isoDate).getTime();
	const mins = Math.floor(diff / 60000);
	if (mins < 1) return "just now";
	if (mins < 60) return `${mins}m ago`;
	const hours = Math.floor(mins / 60);
	return `${hours}h ago`;
}

export function DeviceStatus() {
	const { data: heartbeat } = useDeviceHeartbeat();

	if (!heartbeat?.last_seen) return null;

	const lastSeen = new Date(heartbeat.last_seen);
	const isOnline = Date.now() - lastSeen.getTime() < 5 * 60 * 1000; // 5 min threshold

	return (
		<div className="rounded-md border border-border/40 bg-secondary/10 px-3 py-2">
			<div className="flex items-center gap-2">
				{isOnline ? (
					<Wifi className="w-3 h-3 text-success" />
				) : (
					<WifiOff className="w-3 h-3 text-muted-foreground/40" />
				)}
				<span className="text-[10px] uppercase tracking-widest text-muted-foreground flex-1">
					Wall Clock
				</span>
				<span className="text-[10px] text-muted-foreground/60">
					{formatTimeAgo(heartbeat.last_seen)}
				</span>
			</div>
			{heartbeat.battery_voltage && (
				<div className="flex items-center gap-1.5 mt-1">
					<Battery className="w-3 h-3 text-muted-foreground/40" />
					<span className="text-[10px] tabular-nums text-muted-foreground">
						{heartbeat.battery_voltage.toFixed(1)}V
					</span>
					{heartbeat.wifi_rssi && (
						<span className="text-[10px] tabular-nums text-muted-foreground/50 ml-auto">
							{heartbeat.wifi_rssi}dBm
						</span>
					)}
				</div>
			)}
		</div>
	);
}
