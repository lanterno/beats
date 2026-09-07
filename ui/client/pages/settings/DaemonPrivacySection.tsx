import { Eye } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { del, get } from "@/shared/api";

interface SignalSummaryInfo {
	id: string;
	hour: string;
	categories: Record<string, number>;
	total_samples: number;
	idle_samples: number;
}

export function DaemonPrivacySection() {
	const [summaries, setSummaries] = useState<SignalSummaryInfo[]>([]);
	const [deleting, setDeleting] = useState(false);
	const [confirmDelete, setConfirmDelete] = useState(false);

	const fetchSummaries = useCallback(async () => {
		try {
			const now = new Date();
			const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
			const data = await get<SignalSummaryInfo[]>(
				`/api/signals/summaries?start=${dayAgo.toISOString()}&end=${now.toISOString()}`,
			);
			setSummaries(data);
		} catch {
			// non-critical
		}
	}, []);

	useEffect(() => {
		fetchSummaries();
	}, [fetchSummaries]);

	// Aggregate categories across all summaries
	const categoryTotals: Record<string, number> = {};
	let totalSamples = 0;
	let idleSamples = 0;
	for (const s of summaries) {
		totalSamples += s.total_samples;
		idleSamples += s.idle_samples;
		for (const [cat, count] of Object.entries(s.categories)) {
			categoryTotals[cat] = (categoryTotals[cat] || 0) + count;
		}
	}

	const handleDeleteAll = async () => {
		setDeleting(true);
		try {
			await del("/api/signals/all");
			setSummaries([]);
			setConfirmDelete(false);
			toast.success("All signal data deleted");
		} catch {
			toast.error("Failed to delete signals");
		} finally {
			setDeleting(false);
		}
	};

	const handleExport = async () => {
		try {
			const now = new Date();
			const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
			const data = await get<SignalSummaryInfo[]>(
				`/api/signals/summaries?start=${dayAgo.toISOString()}&end=${now.toISOString()}`,
			);
			const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
			const url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = `beats-signals-${now.toISOString().slice(0, 10)}.json`;
			a.click();
			URL.revokeObjectURL(url);
		} catch {
			toast.error("Failed to export signals");
		}
	};

	const sortedCategories = Object.entries(categoryTotals).sort(([, a], [, b]) => b - a);

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Eye className="w-4 h-4 text-accent" />
				Signal Privacy
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-4">
				<p className="text-xs text-muted-foreground">
					The daemon sends only aggregated category counts and flow scores. No raw content,
					keystrokes, or window titles are ever transmitted.
				</p>

				{totalSamples > 0 ? (
					<div className="space-y-3">
						<p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider">
							Last 24 hours
						</p>
						<div className="grid grid-cols-2 gap-2">
							{sortedCategories.map(([cat, count]) => (
								<div key={cat} className="flex items-center justify-between text-xs">
									<span className="text-foreground capitalize">{cat}</span>
									<span className="text-muted-foreground tabular-nums">{count} samples</span>
								</div>
							))}
							<div className="flex items-center justify-between text-xs">
								<span className="text-foreground">Idle</span>
								<span className="text-muted-foreground tabular-nums">{idleSamples} samples</span>
							</div>
						</div>
						<p className="text-[10px] text-muted-foreground">
							Total: {totalSamples} samples across {summaries.length} hours
						</p>
					</div>
				) : (
					<p className="text-xs text-muted-foreground/60">No signal data in the last 24 hours.</p>
				)}

				<div className="flex gap-2 pt-2 border-t border-border/50">
					<button
						type="button"
						onClick={handleExport}
						className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/50 transition-colors"
					>
						Export 24h (JSON)
					</button>
					{confirmDelete ? (
						<div className="flex items-center gap-2">
							<button
								type="button"
								onClick={handleDeleteAll}
								disabled={deleting}
								className="px-3 py-1.5 text-xs rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
							>
								{deleting ? "Deleting..." : "Confirm delete"}
							</button>
							<button
								type="button"
								onClick={() => setConfirmDelete(false)}
								className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/50 transition-colors"
							>
								Cancel
							</button>
						</div>
					) : (
						<button
							type="button"
							onClick={() => setConfirmDelete(true)}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
						>
							Delete all signals
						</button>
					)}
				</div>
			</div>
		</section>
	);
}
