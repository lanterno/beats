import { Cpu } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { del, get, post } from "@/shared/api";

export interface DeviceRegistrationInfo {
	id: string;
	device_id: string;
	device_name: string | null;
	created_at: string;
	last_seen: string | null;
}

export function DaemonSection() {
	const [code, setCode] = useState<string | null>(null);
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

	const handleGenerateCode = async () => {
		setLoading(true);
		try {
			const data = await post<{ code: string; expires_in_seconds: number }>(
				"/api/device/pair/code",
			);
			setCode(data.code);
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
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Cpu className="w-4 h-4 text-accent" />
				Daemon
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-4">
				<p className="text-xs text-muted-foreground">
					Pair the <code className="text-accent">beatsd</code> daemon to this account for ambient
					flow tracking. Run <code className="text-accent">beatsd pair &lt;code&gt;</code> within 5
					minutes.
				</p>

				{code ? (
					<div className="space-y-2">
						<div className="font-mono text-2xl tracking-[0.3em] text-accent font-bold">{code}</div>
						<p className="text-[10px] text-muted-foreground">Expires in 5 minutes. One-time use.</p>
						<button
							type="button"
							onClick={() => setCode(null)}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/50 transition-colors"
						>
							Dismiss
						</button>
					</div>
				) : (
					<button
						type="button"
						onClick={handleGenerateCode}
						disabled={loading}
						className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors disabled:opacity-50"
					>
						{loading ? "Generating..." : "Pair new device"}
					</button>
				)}

				{devices.length > 0 && (
					<div className="space-y-2 pt-2 border-t border-border/50">
						<p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider">
							Paired devices
						</p>
						{devices.map((d) => (
							<div key={d.device_id} className="flex items-center justify-between text-xs">
								<div>
									<span className="text-foreground">{d.device_name || "Unnamed device"}</span>
									{d.last_seen && (
										<span className="text-muted-foreground ml-2">
											last seen {new Date(d.last_seen).toLocaleDateString()}
										</span>
									)}
								</div>
								<button
									type="button"
									onClick={() => handleRevoke(d.device_id)}
									disabled={revoking === d.device_id}
									className="px-2 py-1 text-[10px] rounded border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors disabled:opacity-50"
								>
									{revoking === d.device_id ? "Revoking..." : "Revoke"}
								</button>
							</div>
						))}
					</div>
				)}
			</div>
		</section>
	);
}
