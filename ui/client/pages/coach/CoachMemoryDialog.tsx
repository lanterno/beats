/**
 * Coach Memory dialog — view what the coach remembers about the user, rewrite
 * it from recent activity, delete it, or wipe all coach data. Surfaces the
 * privacy/control endpoints (GET/DELETE /api/coach/memory, /memory/rewrite,
 * DELETE /api/coach/data) that previously had no UI.
 */

import { Loader2, RefreshCw, Trash2, TriangleAlert } from "lucide-react";
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
import { Button, Dialog } from "@/shared/ui";

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

	// The Dialog primitive owns the veil, Escape, the focus trap and the close
	// button the hand-rolled modal used to reimplement.
	return (
		<Dialog
			open={open}
			onClose={onClose}
			title="Coach memory"
			description="What the coach remembers about you, built from your recent activity."
		>
			<div className="rounded-[1.125rem] bg-secondary p-3.5 max-h-64 overflow-y-auto mb-4">
				{isLoading ? (
					<div className="flex justify-center py-6 text-muted-foreground">
						<Loader2 className="w-4 h-4 animate-spin" />
					</div>
				) : content ? (
					<>
						<div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
							{content}
						</div>
						{memory?.updated_at && (
							<p className="mt-2 text-[11.5px] font-medium text-muted-foreground">
								Updated {formatDate(memory.updated_at)}
							</p>
						)}
					</>
				) : (
					<p className="text-sm text-muted-foreground py-4 text-center">
						The coach hasn't built any memory yet. It learns from your sessions, briefs, and reviews
						over time.
					</p>
				)}
			</div>

			<div className="flex flex-wrap items-center gap-2">
				<Button
					type="button"
					variant="secondary"
					size="sm"
					onClick={handleRewrite}
					disabled={rewrite.isPending}
				>
					{rewrite.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />}
					Rewrite from recent activity
				</Button>

				{confirm === "memory" ? (
					<div className="flex items-center gap-2">
						<Button
							type="button"
							variant="destructive"
							size="sm"
							onClick={handleDeleteMemory}
							disabled={deleteMemory.isPending}
						>
							Confirm delete
						</Button>
						<Button type="button" variant="secondary" size="sm" onClick={() => setConfirm(null)}>
							Cancel
						</Button>
					</div>
				) : (
					<Button
						type="button"
						variant="ghost"
						size="sm"
						className="text-destructive-ink hover:text-destructive-ink"
						onClick={() => setConfirm("memory")}
						disabled={!content}
					>
						<Trash2 />
						Delete memory
					</Button>
				)}
			</div>

			{/* Danger zone — wipe everything the coach has stored. */}
			<div className="mt-4 pt-4 border-t border-border">
				{confirm === "all" ? (
					<div className="rounded-[1.125rem] bg-destructive/10 p-3.5">
						<div className="flex items-start gap-2">
							<TriangleAlert className="w-4 h-4 text-destructive-ink shrink-0 mt-0.5" />
							<div className="flex-1">
								<p className="text-sm text-foreground">
									Delete all coach data — memory, briefs, reviews, conversations, and usage. This
									cannot be undone.
								</p>
								<div className="flex flex-wrap items-center gap-2 mt-2.5">
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
										variant="secondary"
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
						className="text-[12.5px] font-bold text-destructive-ink hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
					>
						Delete all coach data…
					</button>
				)}
			</div>
		</Dialog>
	);
}
