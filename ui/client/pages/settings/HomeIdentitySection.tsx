import { KeyRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import type { SSOConfig, SSOLinkInfo } from "@/features/auth";
import { describeError } from "@/shared/api";

export function HomeIdentitySection() {
	const [sso, setSso] = useState<SSOConfig | null>(null);
	const [link, setLink] = useState<SSOLinkInfo | null>(null);
	const [busy, setBusy] = useState(false);

	const load = useCallback(async () => {
		const { getSsoConfig, getCurrentUser } = await import("@/features/auth");
		const cfg = await getSsoConfig();
		setSso(cfg);
		if (!cfg.enabled) return;
		try {
			setLink((await getCurrentUser()).sso);
		} catch {
			setLink(null);
		}
	}, []);

	useEffect(() => {
		load();
	}, [load]);

	const handleLink = async () => {
		if (!sso) return;
		setBusy(true);
		try {
			const { linkSsoIdentity } = await import("@/features/auth");
			const user = await linkSsoIdentity();
			setLink(user.sso);
			toast.success(`Linked ${sso.provider_name} identity`);
		} catch (err) {
			const failure = err as Error & { code?: string };
			// No cookie here yet — go and get one, then come straight back
			// to this page rather than to the login screen.
			if (failure.code === "SSO_NO_SESSION" && sso.login_url) {
				const returnTo = `${window.location.origin}${window.location.pathname}`;
				window.location.href = `${sso.login_url}/?return_to=${encodeURIComponent(returnTo)}`;
				return;
			}
			toast.error(describeError(err, "Failed to link identity"));
		} finally {
			setBusy(false);
		}
	};

	const handleUnlink = async () => {
		setBusy(true);
		try {
			const { unlinkSsoIdentity } = await import("@/features/auth");
			const user = await unlinkSsoIdentity();
			setLink(user.sso);
			toast.success("Identity unlinked");
		} catch (err) {
			toast.error(describeError(err, "Failed to unlink identity"));
		} finally {
			setBusy(false);
		}
	};

	if (!sso?.enabled) return null;

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<KeyRound className="w-4 h-4 text-accent" />
				{sso.provider_name} identity
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Link your {sso.provider_name} identity to sign in here with it, alongside your passkeys.
					Linking never replaces them — either way in keeps working.
				</p>

				{link?.linked ? (
					<>
						<div className="flex items-center gap-2 bg-secondary/30 rounded px-2.5 py-1.5">
							<KeyRound className="w-3.5 h-3.5 text-accent/60 shrink-0" />
							<span className="text-xs text-foreground font-medium truncate flex-1">
								{link.holder_name || "Linked device"}
							</span>
							{link.roles.length > 0 && (
								<span className="text-[10px] text-muted-foreground shrink-0">
									{link.roles.join(", ")}
								</span>
							)}
						</div>
						<p className="text-[10px] text-muted-foreground/60 font-mono break-all">{link.did}</p>
						<button
							type="button"
							onClick={handleUnlink}
							disabled={busy}
							className="text-xs text-muted-foreground hover:text-destructive transition-colors disabled:opacity-40"
						>
							{busy ? "Working..." : "Unlink"}
						</button>
					</>
				) : (
					<button
						type="button"
						onClick={handleLink}
						disabled={busy}
						className="text-xs text-accent hover:text-accent/80 transition-colors disabled:opacity-40"
					>
						{busy ? "Linking..." : `Link my ${sso.provider_name} identity`}
					</button>
				)}
			</div>
		</section>
	);
}
