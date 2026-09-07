import { Fingerprint, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import type { CredentialInfo } from "@/features/auth";
import { describeError } from "@/shared/api";

export function PasskeysSection() {
	const [credentials, setCredentials] = useState<CredentialInfo[]>([]);
	const [loadError, setLoadError] = useState(false);
	const [deleting, setDeleting] = useState<string | null>(null);

	const loadCredentials = useCallback(async () => {
		try {
			setLoadError(false);
			const { listCredentials } = await import("@/features/auth");
			setCredentials(await listCredentials());
		} catch {
			setLoadError(true);
		}
	}, []);

	useEffect(() => {
		loadCredentials();
	}, [loadCredentials]);

	const handleDelete = async (id: string) => {
		setDeleting(id);
		try {
			const { deleteCredential } = await import("@/features/auth");
			await deleteCredential(id);
			await loadCredentials();
			toast.success("Passkey removed");
		} catch (err) {
			toast.error(describeError(err, "Failed to remove passkey"));
		} finally {
			setDeleting(null);
		}
	};

	const formatDate = (iso: string) => {
		try {
			return new Date(iso).toLocaleDateString(undefined, {
				year: "numeric",
				month: "short",
				day: "numeric",
			});
		} catch {
			return iso;
		}
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Fingerprint className="w-4 h-4 text-accent" />
				Passkeys
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Passkeys let you sign in securely without a password. You must keep at least one
					registered.
				</p>

				{credentials.length === 0 && !loadError && (
					<p className="text-xs text-muted-foreground/60 italic">Loading...</p>
				)}

				{loadError && (
					<div className="flex items-center gap-2">
						<p className="text-xs text-destructive">Failed to load passkeys.</p>
						<button
							type="button"
							onClick={loadCredentials}
							className="text-xs text-accent hover:text-accent/80 transition-colors"
						>
							Retry
						</button>
					</div>
				)}

				{credentials.length > 0 && (
					<div className="space-y-1.5">
						{credentials.map((cred) => (
							<div
								key={cred.id}
								className="flex items-center gap-2 bg-secondary/30 rounded px-2.5 py-1.5"
							>
								<Fingerprint className="w-3.5 h-3.5 text-accent/60 shrink-0" />
								<span className="text-xs text-foreground font-medium truncate flex-1">
									{cred.device_name || "Unnamed passkey"}
								</span>
								<span className="text-[10px] text-muted-foreground shrink-0">
									{formatDate(cred.created_at)}
								</span>
								{credentials.length > 1 && (
									<button
										type="button"
										onClick={() => handleDelete(cred.id)}
										disabled={deleting === cred.id}
										className="p-1 text-muted-foreground/40 hover:text-destructive transition-colors shrink-0 disabled:opacity-40"
										title="Remove passkey"
									>
										<Trash2 className="w-3 h-3" />
									</button>
								)}
							</div>
						))}
					</div>
				)}
			</div>
		</section>
	);
}
