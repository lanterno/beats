import { Eye } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { del, get } from "@/shared/api";
import { Button, Panel } from "@/shared/ui";
import { DANGER_HOVER, HEADING, HEADING_ICON, LABEL, LEAD } from "./styles";

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
			<h2 className={HEADING}>
				<Eye className={HEADING_ICON} />
				Signal Privacy
			</h2>
			<Panel padding="p-5" className="space-y-4">
				<p className={LEAD}>
					The daemon sends only aggregated category counts and flow scores. No raw content,
					keystrokes, or window titles are ever transmitted.
				</p>

				{totalSamples > 0 ? (
					<div className="space-y-3">
						<p className={LABEL}>Last 24 hours</p>
						<div className="grid grid-cols-2 gap-x-6 gap-y-2">
							{sortedCategories.map(([cat, count]) => (
								<div key={cat} className="flex items-center justify-between gap-2 text-[12.5px]">
									<span className="text-foreground font-medium capitalize">{cat}</span>
									<span className="text-muted-foreground font-mono font-medium">
										{count} samples
									</span>
								</div>
							))}
							<div className="flex items-center justify-between gap-2 text-[12.5px]">
								<span className="text-foreground font-medium">Idle</span>
								<span className="text-muted-foreground font-mono font-medium">
									{idleSamples} samples
								</span>
							</div>
						</div>
						<p className="text-[11px] font-medium text-muted-foreground">
							Total: {totalSamples} samples across {summaries.length} hours
						</p>
					</div>
				) : (
					<p className="text-[12.5px] text-muted-foreground">
						No signal data in the last 24 hours.
					</p>
				)}

				<div className="flex flex-wrap gap-2 pt-4 border-t border-border">
					<Button variant="secondary" size="sm" onClick={handleExport}>
						Export 24h (JSON)
					</Button>
					{confirmDelete ? (
						<div className="flex items-center gap-2">
							<Button variant="destructive" size="sm" onClick={handleDeleteAll} disabled={deleting}>
								{deleting ? "Deleting..." : "Confirm delete"}
							</Button>
							<Button variant="secondary" size="sm" onClick={() => setConfirmDelete(false)}>
								Cancel
							</Button>
						</div>
					) : (
						<Button
							variant="secondary"
							size="sm"
							onClick={() => setConfirmDelete(true)}
							className={DANGER_HOVER}
						>
							Delete all signals
						</Button>
					)}
				</div>
			</Panel>
		</section>
	);
}
