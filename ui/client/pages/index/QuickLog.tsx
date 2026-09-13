/**
 * QuickLog Component
 * Manual session entry: project, date, start/end. No note/tags — the app
 * takes no free-text input; tags are auto-derived from daemon flow signals.
 */

import { useQueryClient } from "@tanstack/react-query";
import { Check, Plus, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { toast } from "sonner";
import { ProjectPicker, projectKeys, useProjects, visibleProjects } from "@/entities/project";
import { sessionKeys } from "@/entities/session";
import { post } from "@/shared/api";
import { isValidTimeRange, toLocalDatetimeLocalString } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";

const LABEL = "font-body text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground";

// The mockup's `.dlg input`: a wash, no border, the figures face.
const FIELD =
	"w-full rounded-xl bg-secondary px-2.5 py-1.5 text-xs font-mono font-bold text-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent";

export function QuickLog() {
	const fieldId = useId();
	const [open, setOpen] = useState(false);
	const { data: projects } = useProjects();
	const queryClient = useQueryClient();

	const [projectId, setProjectId] = useState("");
	const [startTime, setStartTime] = useState(() =>
		toLocalDatetimeLocalString(new Date(Date.now() - 60 * 60 * 1000)),
	);
	const [endTime, setEndTime] = useState(() => toLocalDatetimeLocalString(new Date()));
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
			});
			queryClient.invalidateQueries({ queryKey: sessionKeys.all });
			// A beat moves the project's week, its ledger and its balance too.
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
			toast("Session logged");
			setOpen(false);
		} catch {
			toast.error("Failed to log session");
		} finally {
			setSaving(false);
		}
	};

	if (!open) {
		return (
			<button
				type="button"
				onClick={() => setOpen(true)}
				// On the sky: the header's chip, the panel with ink on it.
				className="inline-flex items-center gap-1.5 rounded-full bg-sidebar px-3 py-1 text-xs font-bold text-foreground shadow-soft hover:bg-card transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				title="Log a past session"
			>
				<Plus className="w-3.5 h-3.5" />
				Quick log
			</button>
		);
	}

	return (
		<Panel
			padding="px-5 py-4"
			className="space-y-2.5"
			style={{ animation: "fadeSlideIn 150ms ease-out both" }}
		>
			<div className="flex items-center justify-between">
				<span className={LABEL}>Log a session</span>
				<button
					type="button"
					onClick={() => setOpen(false)}
					className="grid place-items-center w-6 h-6 -my-1 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
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
					<label htmlFor={`${fieldId}-start`} className={`${LABEL} block mb-1`}>
						Start
					</label>
					<input
						id={`${fieldId}-start`}
						type="datetime-local"
						value={startTime}
						onChange={(e) => setStartTime(e.target.value)}
						className={FIELD}
					/>
				</div>
				<div>
					<label htmlFor={`${fieldId}-end`} className={`${LABEL} block mb-1`}>
						End
					</label>
					<input
						id={`${fieldId}-end`}
						type="datetime-local"
						value={endTime}
						onChange={(e) => setEndTime(e.target.value)}
						className={FIELD}
					/>
				</div>
			</div>

			{!validRange && (
				<p className="text-xs font-medium text-destructive-ink" role="alert">
					End time must be after the start time.
				</p>
			)}

			<Button
				type="button"
				size="sm"
				onClick={handleSave}
				disabled={!projectId || !validRange || saving}
				className="w-full"
			>
				<Check className="w-3 h-3" />
				Log Session
			</Button>
		</Panel>
	);
}
