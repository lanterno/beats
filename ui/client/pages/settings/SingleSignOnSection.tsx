import { KeyRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import type { LinkedIdentity, SSOProvider } from "@/features/auth";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { HEADING, HEADING_ICON, LEAD, LINKISH } from "./styles";

interface Row {
	id: string;
	name: string;
	linked: LinkedIdentity | null;
	/** False for an identity whose provider this instance no longer offers. */
	offered: boolean;
}

/**
 * One row per provider this instance offers, plus any identity linked through
 * a provider it has since dropped — still listed, so it can be unlinked.
 */
function rows(providers: SSOProvider[], identities: LinkedIdentity[]): Row[] {
	const offered: Row[] = providers.map((p) => ({
		id: p.id,
		name: p.name,
		linked: identities.find((i) => i.provider === p.id) ?? null,
		offered: true,
	}));
	const dropped: Row[] = identities
		.filter((i) => !providers.some((p) => p.id === i.provider))
		.map((i) => ({ id: i.provider, name: i.provider_name, linked: i, offered: false }));
	return [...offered, ...dropped];
}

export function SingleSignOnSection() {
	const [providers, setProviders] = useState<SSOProvider[]>([]);
	const [identities, setIdentities] = useState<LinkedIdentity[]>([]);
	const [busy, setBusy] = useState<string | null>(null);

	const load = useCallback(async () => {
		const { getSsoProviders, getCurrentUser } = await import("@/features/auth");
		setProviders(await getSsoProviders());
		try {
			setIdentities((await getCurrentUser()).identities);
		} catch {
			setIdentities([]);
		}
	}, []);

	useEffect(() => {
		load();
	}, [load]);

	const handleLink = async (row: Row) => {
		setBusy(row.id);
		try {
			const { startSsoLink } = await import("@/features/auth");
			// Leaves for the provider; `/auth/callback` brings the browser back here.
			await startSsoLink(row.id);
		} catch (err) {
			toast.error(describeError(err, `Couldn't reach ${row.name}`));
			setBusy(null);
		}
	};

	const handleUnlink = async (row: Row) => {
		setBusy(row.id);
		try {
			const { unlinkSsoIdentity } = await import("@/features/auth");
			setIdentities((await unlinkSsoIdentity(row.id)).identities);
			toast.success(`${row.name} unlinked`);
		} catch (err) {
			toast.error(describeError(err, "Failed to unlink"));
		} finally {
			setBusy(null);
		}
	};

	const list = rows(providers, identities);
	if (list.length === 0) return null;

	return (
		<section className="mb-8">
			<h2 className={HEADING}>
				<KeyRound className={HEADING_ICON} />
				Single sign-on
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>
					Link an account you have elsewhere to sign in here with it, alongside your passkeys.
					Linking never replaces them — either way in keeps working.
				</p>
				<ul className="divide-y divide-border">
					{list.map((row) => (
						<li key={row.id} className="flex items-center gap-3 py-2.5">
							<div className="min-w-0 flex-1">
								<p className="text-[13px] font-bold text-foreground truncate">{row.name}</p>
								{row.linked && (
									<p className="text-[11.5px] text-muted-foreground truncate">
										{row.linked.email || row.linked.name || "Linked"}
										{!row.offered && " · no longer offered here"}
									</p>
								)}
							</div>
							{row.linked ? (
								<button
									type="button"
									onClick={() => handleUnlink(row)}
									disabled={busy !== null}
									className={cn(LINKISH, "text-muted-foreground hover:text-destructive-ink")}
								>
									{busy === row.id ? "Working..." : "Unlink"}
								</button>
							) : (
								<button
									type="button"
									onClick={() => handleLink(row)}
									disabled={busy !== null}
									className={LINKISH}
								>
									{busy === row.id ? "Opening..." : "Link"}
								</button>
							)}
						</li>
					))}
				</ul>
			</Panel>
		</section>
	);
}
