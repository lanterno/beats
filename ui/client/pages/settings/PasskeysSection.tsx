import { Fingerprint, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import type { CredentialInfo } from "@/features/auth";
import { describeError } from "@/shared/api";
import { Panel } from "@/shared/ui";
import { HEADING, HEADING_ICON, LEAD, LINKISH, LIST, REMOVE, ROW } from "./styles";

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
			<h2 className={HEADING}>
				<Fingerprint className={HEADING_ICON} />
				Passkeys
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>
					Passkeys let you sign in securely without a password. You must keep at least one
					registered.
				</p>

				{credentials.length === 0 && !loadError && <p className={LEAD}>Loading...</p>}

				{loadError && (
					<div className="flex items-center gap-2">
						<p className="text-[12.5px] text-destructive-ink">Failed to load passkeys.</p>
						<button type="button" onClick={loadCredentials} className={LINKISH}>
							Retry
						</button>
					</div>
				)}

				{credentials.length > 0 && (
					<div className={LIST}>
						{credentials.map((cred) => (
							<div key={cred.id} className={ROW}>
								<Fingerprint className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
								<span className="text-foreground font-bold truncate flex-1">
									{cred.device_name || "Unnamed passkey"}
								</span>
								<span className="text-[11.5px] font-medium text-muted-foreground shrink-0">
									{formatDate(cred.created_at)}
								</span>
								{credentials.length > 1 && (
									<button
										type="button"
										onClick={() => handleDelete(cred.id)}
										disabled={deleting === cred.id}
										className={REMOVE}
										title="Remove passkey"
									>
										<Trash2 className="w-3 h-3" />
									</button>
								)}
							</div>
						))}
					</div>
				)}
			</Panel>
		</section>
	);
}
