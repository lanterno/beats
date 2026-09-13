import { KeyRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import type { SSOConfig, SSOLinkInfo } from "@/features/auth";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { HEADING, HEADING_ICON, LEAD, LINKISH } from "./styles";

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
			<h2 className={HEADING}>
				<KeyRound className={HEADING_ICON} />
				{sso.provider_name} identity
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>
					Link your {sso.provider_name} identity to sign in here with it, alongside your passkeys.
					Linking never replaces them — either way in keeps working.
				</p>

				{link?.linked ? (
					<>
						<div className="flex items-center gap-2 rounded-xl bg-secondary px-3 py-2">
							<KeyRound className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
							<span className="text-[12.5px] text-foreground font-bold truncate flex-1">
								{link.holder_name || "Linked device"}
							</span>
							{link.roles.length > 0 && (
								<span className="text-[11px] text-muted-foreground shrink-0">
									{link.roles.join(", ")}
								</span>
							)}
						</div>
						<p className="text-[11px] text-muted-foreground font-code break-all">{link.did}</p>
						<button
							type="button"
							onClick={handleUnlink}
							disabled={busy}
							className={cn(LINKISH, "text-muted-foreground hover:text-destructive-ink")}
						>
							{busy ? "Working..." : "Unlink"}
						</button>
					</>
				) : (
					<button type="button" onClick={handleLink} disabled={busy} className={LINKISH}>
						{busy ? "Linking..." : `Link my ${sso.provider_name} identity`}
					</button>
				)}
			</Panel>
		</section>
	);
}
