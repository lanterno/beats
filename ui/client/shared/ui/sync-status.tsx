/**
 * SyncStatus — header badge showing the offline mutation queue state.
 *
 * Three visual states:
 *   - green dot: fully synced and online
 *   - amber spinner: currently syncing (draining the queue)
 *   - red dot + count: offline or queued work pending
 *
 * Kept tiny on purpose — a full queue-inspector drawer would belong in
 * Settings, not the header. For now, a tooltip on hover is enough context.
 */

import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { cn, useSyncStatus } from "@/shared/lib";

interface SyncStatusProps {
	className?: string;
	/** Always show the badge, even when fully synced. Defaults to false. */
	verbose?: boolean;
}

export function SyncStatus({ className, verbose = false }: SyncStatusProps) {
	const { pendingCount, syncing, online, lastError } = useSyncStatus();

	if (syncing) {
		return (
			<span
				className={cn(
					"inline-flex items-center gap-1.5 text-[11px] text-muted-foreground",
					className,
				)}
				title="Syncing queued changes…"
			>
				<Loader2 className="w-3 h-3 animate-spin" />
				<span>Syncing…</span>
			</span>
		);
	}

	if (!online || pendingCount > 0) {
		const label = !online
			? `Offline · ${pendingCount} pending`
			: `${pendingCount} pending${lastError ? " (retrying)" : ""}`;
		return (
			<span
				className={cn("inline-flex items-center gap-1.5 text-[11px] text-amber-500", className)}
				title={lastError ?? label}
			>
				<AlertCircle className="w-3 h-3" />
				<span>{label}</span>
			</span>
		);
	}

	if (!verbose) return null;

	return (
		<span
			className={cn(
				"inline-flex items-center gap-1.5 text-[11px] text-muted-foreground/70",
				className,
			)}
			title="All changes synced"
		>
			<CheckCircle2 className="w-3 h-3 text-emerald-500" />
			<span>Synced</span>
		</span>
	);
}
