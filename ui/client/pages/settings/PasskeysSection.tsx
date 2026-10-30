import { Fingerprint, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import type { CredentialInfo } from "@/features/auth";
import { describeError } from "@/shared/api";
import { type ConfirmRequest, Panel, useConfirm } from "@/shared/ui";
import { HEADING, HEADING_ICON, LEAD, LINKISH, LIST, REMOVE, ROW } from "./styles";

function formatDate(iso: string) {
	try {
		return new Date(iso).toLocaleDateString(undefined, {
			year: "numeric",
			month: "short",
			day: "numeric",
		});
	} catch {
		return iso;
	}
}

/**
 * What removing a passkey costs, asked before it happens: the passkey by name and
 * date (two can share a device's name), and the one left when only one will be.
 */
function removalQuestion(passkey: CredentialInfo, others: CredentialInfo[]): ConfirmRequest {
	const sentences = [
		`Added ${formatDate(passkey.created_at)}, it stops signing you in on every device that holds it.`,
	];
	if (others.length === 1) {
		const [last] = others;
		sentences.push(
			last.device_name
				? `The ${last.device_name} passkey will be the only one left.`
				: "Your other passkey will be the only one left.",
		);
	}
	return {
		title: passkey.device_name
			? `Remove the ${passkey.device_name} passkey?`
			: "Remove this passkey?",
		detail: sentences.join(" "),
		confirmLabel: "Remove",
		cancelLabel: "Keep it",
		tone: "danger",
	};
}

export function PasskeysSection() {
	// null until the first load answers, so an account with no passkeys (one that signs in
	// through single sign-on) isn't mistaken for one still loading.
	const [credentials, setCredentials] = useState<CredentialInfo[] | null>(null);
	const [loadError, setLoadError] = useState(false);
	const [deleting, setDeleting] = useState<string | null>(null);
	const { confirm, confirmDialog } = useConfirm();

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

	const handleDelete = async (passkey: CredentialInfo, all: CredentialInfo[]) => {
		setDeleting(passkey.id);
		try {
			const others = all.filter((cred) => cred.id !== passkey.id);
			const ok = await confirm(removalQuestion(passkey, others));
			if (!ok) return;
			const { deleteCredential } = await import("@/features/auth");
			await deleteCredential(passkey.id);
			await loadCredentials();
			toast.success("Passkey removed");
		} catch (err) {
			toast.error(describeError(err, "Failed to remove passkey"));
		} finally {
			setDeleting(null);
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
					Passkeys let you sign in securely without a password.
					{credentials?.length ? " You must keep at least one registered." : null}
				</p>

				{credentials === null && !loadError && <p className={LEAD}>Loading...</p>}

				{credentials?.length === 0 && (
					<p className={LEAD}>No passkeys on this account. It signs in through single sign-on.</p>
				)}

				{loadError && (
					<div className="flex items-center gap-2">
						<p className="text-[12.5px] text-destructive-ink">Failed to load passkeys.</p>
						<button type="button" onClick={loadCredentials} className={LINKISH}>
							Retry
						</button>
					</div>
				)}

				{credentials && credentials.length > 0 && (
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
										onClick={() => handleDelete(cred, credentials)}
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
			{confirmDialog}
		</section>
	);
}
