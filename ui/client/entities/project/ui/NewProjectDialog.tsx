/**
 * New Project Dialog
 * Lightweight modal that creates a project. Wired into the sidebar and the
 * dashboard's empty state so a fresh user has a path to their first project.
 */

import { FolderPlus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { describeError } from "@/shared/api";
import { Button } from "@/shared/ui";
import { useCreateProject } from "../api";
import type { Project } from "../model";
import { toProject } from "../model";

interface NewProjectDialogProps {
	open: boolean;
	onClose: () => void;
	/** Called with the created project after a successful save. */
	onCreated?: (project: Project) => void;
}

export function NewProjectDialog({ open, onClose, onCreated }: NewProjectDialogProps) {
	const [name, setName] = useState("");
	const [weeklyGoal, setWeeklyGoal] = useState("");
	const nameRef = useRef<HTMLInputElement>(null);
	const createProjectMutation = useCreateProject();

	// Reset fields and focus the name field each time the dialog opens.
	useEffect(() => {
		if (!open) return;
		setName("");
		setWeeklyGoal("");
		const id = requestAnimationFrame(() => nameRef.current?.focus());
		return () => cancelAnimationFrame(id);
	}, [open]);

	// Close on Escape.
	useEffect(() => {
		if (!open) return;
		const onKey = (e: KeyboardEvent) => {
			if (e.key === "Escape") onClose();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open, onClose]);

	if (!open) return null;

	const trimmed = name.trim();

	const handleSubmit = async () => {
		if (!trimmed || createProjectMutation.isPending) return;

		let goal: number | null = null;
		if (weeklyGoal.trim() !== "") {
			goal = Number(weeklyGoal);
			if (Number.isNaN(goal) || goal < 0) {
				toast.error("Weekly goal must be a positive number of hours");
				return;
			}
		}

		try {
			const created = await createProjectMutation.mutateAsync({
				name: trimmed,
				weekly_goal: goal,
			});
			toast.success("Project created");
			onClose();
			onCreated?.(toProject(created));
		} catch (err) {
			toast.error(describeError(err, "Failed to create project"));
		}
	};

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
				aria-labelledby="new-project-title"
				className="relative w-full max-w-sm rounded-xl border border-border/80 bg-card p-5 shadow-card"
			>
				<header className="flex items-center gap-2 mb-4">
					<FolderPlus className="w-4 h-4 text-accent" />
					<h2 id="new-project-title" className="text-sm font-semibold text-foreground">
						New project
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

				<form
					onSubmit={(e) => {
						e.preventDefault();
						handleSubmit();
					}}
					className="space-y-4"
				>
					<div>
						<label
							htmlFor="new-project-name"
							className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5"
						>
							Name
						</label>
						<input
							id="new-project-name"
							ref={nameRef}
							value={name}
							onChange={(e) => setName(e.target.value)}
							placeholder="e.g. Deep Work"
							className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
						/>
					</div>
					<div>
						<label
							htmlFor="new-project-goal"
							className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5"
						>
							Weekly goal (hours, optional)
						</label>
						<input
							id="new-project-goal"
							type="number"
							min="0"
							step="0.5"
							value={weeklyGoal}
							onChange={(e) => setWeeklyGoal(e.target.value)}
							placeholder="e.g. 10"
							className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
						/>
					</div>
					<div className="flex gap-2 pt-1">
						<Button
							type="submit"
							disabled={!trimmed || createProjectMutation.isPending}
							className="flex-1"
						>
							{createProjectMutation.isPending ? "Creating..." : "Create project"}
						</Button>
						<Button type="button" variant="outline" onClick={onClose}>
							Cancel
						</Button>
					</div>
				</form>
			</div>
		</div>
	);
}
