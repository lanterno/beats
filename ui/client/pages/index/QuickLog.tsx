/**
 * QuickLog Component
 * Manual session entry: project, date, start/end, optional note.
 */

import { useQueryClient } from "@tanstack/react-query";
import { Check, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ProjectPicker, useProjects, visibleProjects } from "@/entities/project";
import { sessionKeys, useAllTags } from "@/entities/session";
import { post } from "@/shared/api";
import { isValidTimeRange, toLocalDatetimeLocalString } from "@/shared/lib";
import { TagInput } from "@/shared/ui";

export function QuickLog() {
	const [open, setOpen] = useState(false);
	const { data: projects } = useProjects();
	const { data: allTags } = useAllTags();
	const queryClient = useQueryClient();

	const [projectId, setProjectId] = useState("");
	const [startTime, setStartTime] = useState(() =>
		toLocalDatetimeLocalString(new Date(Date.now() - 60 * 60 * 1000)),
	);
	const [endTime, setEndTime] = useState(() => toLocalDatetimeLocalString(new Date()));
	const [note, setNote] = useState("");
	const [tags, setTags] = useState<string[]>([]);
	const [saving, setSaving] = useState(false);

	// Refresh start/end defaults each time the form opens so reopening it later
	// doesn't show stale times captured at mount.
	useEffect(() => {
		if (open) {
			setStartTime(toLocalDatetimeLocalString(new Date(Date.now() - 60 * 60 * 1000)));
			setEndTime(toLocalDatetimeLocalString(new Date()));
		}
	}, [open]);

	const activeProjects = visibleProjects(projects);
	const validRange = isValidTimeRange(startTime, endTime);

	const handleSave = async () => {
		if (!projectId || !validRange) return;
		setSaving(true);
		try {
			await post("/api/beats/", {
				project_id: projectId,
				start: new Date(startTime).toISOString(),
				end: new Date(endTime).toISOString(),
				note: note || null,
				tags,
			});
			queryClient.invalidateQueries({ queryKey: sessionKeys.all });
			toast("Session logged");
			setOpen(false);
			setNote("");
			setTags([]);
		} catch {
			toast.error("Failed to log session");
		} finally {
			setSaving(false);
		}
	};

	if (!open) {
		return (
			<button
				onClick={() => setOpen(true)}
				className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-accent transition-colors"
				title="Log a past session"
			>
				<Plus className="w-3.5 h-3.5" />
				Quick log
			</button>
		);
	}

	return (
		<div
			className="rounded-lg border border-border/80 bg-card shadow-soft p-3 space-y-2"
			style={{ animation: "fadeSlideIn 150ms ease-out both" }}
		>
			<div className="flex items-center justify-between">
				<span className="text-xs font-medium text-foreground">Log a session</span>
				<button
					onClick={() => setOpen(false)}
					className="p-0.5 text-muted-foreground/40 hover:text-muted-foreground transition-colors"
				>
					<X className="w-3 h-3" />
				</button>
			</div>

			<ProjectPicker
				projects={activeProjects}
				value={projectId || null}
				onChange={(id) => setProjectId(id ?? "")}
				compact
				ariaLabel="Project"
			/>

			<div className="grid grid-cols-2 gap-2">
				<div>
					<label className="text-[10px] text-muted-foreground/60">Start</label>
					<input
						type="datetime-local"
						value={startTime}
						onChange={(e) => setStartTime(e.target.value)}
						className="w-full text-xs bg-secondary/50 border border-border rounded px-2 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
					/>
				</div>
				<div>
					<label className="text-[10px] text-muted-foreground/60">End</label>
					<input
						type="datetime-local"
						value={endTime}
						onChange={(e) => setEndTime(e.target.value)}
						className="w-full text-xs bg-secondary/50 border border-border rounded px-2 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
					/>
				</div>
			</div>

			<input
				type="text"
				value={note}
				onChange={(e) => setNote(e.target.value)}
				placeholder="What did you work on? (optional)"
				className="w-full text-xs bg-secondary/50 border border-border rounded px-2 py-1.5 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-accent"
			/>

			<TagInput
				tags={tags}
				onChange={setTags}
				suggestions={allTags ?? []}
				placeholder="Tags (optional)"
			/>

			{!validRange && (
				<p className="text-[11px] text-red-400" role="alert">
					End time must be after the start time.
				</p>
			)}

			<button
				onClick={handleSave}
				disabled={!projectId || !validRange || saving}
				className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium bg-accent text-accent-foreground disabled:opacity-40 hover:bg-accent/85 transition-colors"
			>
				<Check className="w-3 h-3" />
				Log Session
			</button>
		</div>
	);
}
