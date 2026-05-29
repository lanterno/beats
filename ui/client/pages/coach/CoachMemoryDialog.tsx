/**
 * Coach Memory dialog — view what the coach remembers about the user, rewrite
 * it from recent activity, delete it, or wipe all coach data. Surfaces the
 * privacy/control endpoints (GET/DELETE /api/coach/memory, /memory/rewrite,
 * DELETE /api/coach/data) that previously had no UI.
 */

import { Brain, Loader2, RefreshCw, Trash2, TriangleAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
	useCoachMemory,
	useDeleteCoachData,
	useDeleteMemory,
	useRewriteMemory,
} from "@/entities/coach";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Button } from "@/shared/ui";

interface CoachMemoryDialogProps {
	open: boolean;
	onClose: () => void;
}

export function CoachMemoryDialog({ open, onClose }: CoachMemoryDialogProps) {
	const { data: memory, isLoading } = useCoachMemory();
	const rewrite = useRewriteMemory();
	const deleteMemory = useDeleteMemory();
	const deleteAll = useDeleteCoachData();
	// Which destructive action is awaiting confirmation, if any.
	const [confirm, setConfirm] = useState<null | "memory" | "all">(null);

	// Reset the confirm state whenever the dialog re-opens.
	useEffect(() => {
		if (open) setConfirm(null);
	}, [open]);

	useEffect(() => {
		if (!open) return;
		const onKey = (e: KeyboardEvent) => {
			if (e.key === "Escape") onClose();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open, onClose]);

	if (!open) return null;

	const handleRewrite = () => {
		rewrite.mutate(undefined, {
			onSuccess: () => toast.success("Memory rewritten from your recent activity"),
			onError: (err) => toast.error(describeError(err, "Failed to rewrite memory")),
		});
	};

	const handleDeleteMemory = () => {
		deleteMemory.mutate(undefined, {
			onSuccess: () => {
				toast.success("Memory deleted");
				setConfirm(null);
			},
			onError: (err) => toast.error(describeError(err, "Failed to delete memory")),
		});
	};

	const handleDeleteAll = () => {
		deleteAll.mutate(undefined, {
			onSuccess: () => {
				toast.success("All coach data deleted");
				setConfirm(null);
				onClose();
			},
			onError: (err) => toast.error(describeError(err, "Failed to delete coach data")),
		});
	};

	const content = memory?.content?.trim();

	return (
		<div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
			<button
				type="button"
				aria-label="Close"
				className="absolute inset-0 bg-black/50 backdrop-blur-xs"
				onClick={onClose}
			/>
			<div
				role="dialog"
				aria-modal="true"
				aria-labelledby="coach-memory-title"
				className="relative w-full max-w-lg rounded-xl border border-border/80 bg-card p-5 shadow-card"
			>
				<header className="flex items-center gap-2 mb-1">
					<Brain className="w-4 h-4 text-accent" />
					<h2 id="coach-memory-title" className="text-sm font-semibold text-foreground">
						Coach memory
					</h2>
					<button
						type="button"
						onClick={onClose}
						aria-label="Close"
						className="ml-auto p-1 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50 transition"
					>
						<X className="w-4 h-4" />
					</button>
				</header>
				<p className="text-xs text-muted-foreground/70 mb-3">
					What the coach remembers about you, built from your recent activity.
				</p>

				<div className="rounded-lg border border-border/60 bg-secondary/20 p-3 max-h-64 overflow-y-auto mb-4">
					{isLoading ? (
						<div className="flex justify-center py-6 text-muted-foreground/50">
							<Loader2 className="w-4 h-4 animate-spin" />
						</div>
					) : content ? (
						<>
							<div className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
								{content}
							</div>
							{memory?.updated_at && (
								<p className="mt-2 text-[11px] text-muted-foreground/50">
									Updated {formatDate(memory.updated_at)}
								</p>
							)}
						</>
					) : (
						<p className="text-sm text-muted-foreground/60 py-4 text-center">
							The coach hasn't built any memory yet. It learns from your sessions, briefs, and
							reviews over time.
						</p>
					)}
				</div>

				<div className="flex flex-wrap items-center gap-2">
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={handleRewrite}
						disabled={rewrite.isPending}
					>
						{rewrite.isPending ? (
							<Loader2 className="w-3.5 h-3.5 animate-spin" />
						) : (
							<RefreshCw className="w-3.5 h-3.5" />
						)}
						Rewrite from recent activity
					</Button>

					{confirm === "memory" ? (
						<div className="flex items-center gap-1">
							<Button
								type="button"
								variant="destructive"
								size="sm"
								onClick={handleDeleteMemory}
								disabled={deleteMemory.isPending}
							>
								Confirm delete
							</Button>
							<Button type="button" variant="ghost" size="sm" onClick={() => setConfirm(null)}>
								Cancel
							</Button>
						</div>
					) : (
						<Button
							type="button"
							variant="ghost"
							size="sm"
							onClick={() => setConfirm("memory")}
							disabled={!content}
						>
							<Trash2 className="w-3.5 h-3.5" />
							Delete memory
						</Button>
					)}
				</div>

				{/* Danger zone — wipe everything the coach has stored. */}
				<div className="mt-4 pt-4 border-t border-border/40">
					{confirm === "all" ? (
						<div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3">
							<div className="flex items-start gap-2">
								<TriangleAlert className="w-4 h-4 text-destructive shrink-0 mt-0.5" />
								<div className="flex-1">
									<p className="text-sm text-foreground">
										Delete all coach data — memory, briefs, reviews, conversations, and usage. This
										cannot be undone.
									</p>
									<div className="flex items-center gap-1 mt-2">
										<Button
											type="button"
											variant="destructive"
											size="sm"
											onClick={handleDeleteAll}
											disabled={deleteAll.isPending}
										>
											{deleteAll.isPending ? "Deleting..." : "Delete everything"}
										</Button>
										<Button
											type="button"
											variant="ghost"
											size="sm"
											onClick={() => setConfirm(null)}
										>
											Cancel
										</Button>
									</div>
								</div>
							</div>
						</div>
					) : (
						<button
							type="button"
							onClick={() => setConfirm("all")}
							className="text-xs text-destructive/80 hover:text-destructive hover:underline"
						>
							Delete all coach data…
						</button>
					)}
				</div>
			</div>
		</div>
	);
}
