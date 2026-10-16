import { Cpu } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { del, get, post } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { DANGER_HOVER, HEADING, HEADING_ICON, LABEL, LEAD } from "./styles";

export interface DeviceRegistrationInfo {
	id: string;
	device_id: string;
	device_name: string | null;
	created_at: string;
	last_seen: string | null;
}

/** A code on screen, and the wall-clock moment it stops being any use. */
interface PairingCode {
	code: string;
	expiresInSeconds: number;
	/** `Date.now()` milliseconds at which the code is cleared. */
	deadline: number;
}

function expiryLine(seconds: number): string {
	const minutes = Math.max(1, Math.round(seconds / 60));
	return `Expires in ${minutes} ${minutes === 1 ? "minute" : "minutes"}. One-time use.`;
}

export function DaemonSection() {
	const [pairing, setPairing] = useState<PairingCode | null>(null);
	const [loading, setLoading] = useState(false);
	const [devices, setDevices] = useState<DeviceRegistrationInfo[]>([]);
	const [revoking, setRevoking] = useState<string | null>(null);

	const fetchDevices = useCallback(async () => {
		try {
			const data = await get<DeviceRegistrationInfo[]>("/api/device/registrations");
			setDevices(data);
		} catch {
			// Silently ignore — devices list is non-critical
		}
	}, []);

	useEffect(() => {
		fetchDevices();
	}, [fetchDevices]);

	// Clear the code once its deadline passes. The interval alone is not
	// enough: browsers throttle it in a hidden tab and it stalls while the
	// machine sleeps, so the deadline is checked again when the tab comes
	// back. The deadline is wall-clock, not a countdown, for the same reason.
	useEffect(() => {
		if (!pairing) return;
		const { deadline } = pairing;
		const clearIfExpired = () => {
			if (Date.now() >= deadline) setPairing(null);
		};
		const interval = window.setInterval(clearIfExpired, 1000);
		document.addEventListener("visibilitychange", clearIfExpired);
		window.addEventListener("focus", clearIfExpired);
		return () => {
			window.clearInterval(interval);
			document.removeEventListener("visibilitychange", clearIfExpired);
			window.removeEventListener("focus", clearIfExpired);
		};
	}, [pairing]);

	const handleGenerateCode = async () => {
		setLoading(true);
		// Taken before the request, so the deadline falls on or before the
		// server's own expiry and the page never shows a code it has dropped.
		const requestedAt = Date.now();
		try {
			const data = await post<{ code: string; expires_in_seconds: number }>(
				"/api/device/pair/code",
			);
			setPairing({
				code: data.code,
				expiresInSeconds: data.expires_in_seconds,
				deadline: requestedAt + data.expires_in_seconds * 1000,
			});
			toast.success("Pairing code generated");
		} catch {
			toast.error("Failed to generate pairing code");
		} finally {
			setLoading(false);
		}
	};

	const handleRevoke = async (deviceId: string) => {
		setRevoking(deviceId);
		try {
			await del(`/api/device/registrations/${deviceId}`);
			setDevices((prev) => prev.filter((d) => d.device_id !== deviceId));
			toast.success("Device revoked");
		} catch {
			toast.error("Failed to revoke device");
		} finally {
			setRevoking(null);
		}
	};

	return (
		<section className="mb-8">
			<h2 className={HEADING}>
				<Cpu className={HEADING_ICON} />
				Daemon
			</h2>
			<Panel padding="p-5" className="space-y-4">
				<p className={LEAD}>
					Pair the <code className="font-code text-foreground">beatsd</code> daemon to this account
					for ambient flow tracking. Run{" "}
					<code className="font-code text-foreground">beatsd pair &lt;code&gt;</code>.
				</p>

				{pairing ? (
					<div className="space-y-2">
						<div className="font-code text-2xl tracking-[0.3em] text-foreground font-bold">
							{pairing.code}
						</div>
						<p className="text-[11px] font-medium text-muted-foreground">
							{expiryLine(pairing.expiresInSeconds)}
						</p>
						<Button variant="secondary" size="sm" onClick={() => setPairing(null)}>
							Dismiss
						</Button>
					</div>
				) : (
					<Button variant="secondary" size="sm" onClick={handleGenerateCode} disabled={loading}>
						{loading ? "Generating..." : "Pair new device"}
					</Button>
				)}

				{devices.length > 0 && (
					<div className="pt-1">
						<p className={cn(LABEL, "mb-1")}>Paired devices</p>
						{devices.map((d) => (
							<div
								key={d.device_id}
								className="flex items-center justify-between gap-3 py-2 text-[12.5px] border-t border-border"
							>
								<div className="min-w-0">
									<span className="text-foreground font-bold">
										{d.device_name || "Unnamed device"}
									</span>
									{d.last_seen && (
										<span className="text-muted-foreground ml-2">
											last seen {new Date(d.last_seen).toLocaleDateString()}
										</span>
									)}
								</div>
								<Button
									variant="secondary"
									size="sm"
									onClick={() => handleRevoke(d.device_id)}
									disabled={revoking === d.device_id}
									className={cn("h-7 px-3 text-xs shrink-0", DANGER_HOVER)}
								>
									{revoking === d.device_id ? "Revoking..." : "Revoke"}
								</Button>
							</div>
						))}
					</div>
				)}
			</Panel>
		</section>
	);
}
