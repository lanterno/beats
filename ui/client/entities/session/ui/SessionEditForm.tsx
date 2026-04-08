/**
 * Session Edit Form Component
 * Form for editing a work session.
 */

import { Save, X } from "lucide-react";
import { useState } from "react";
import { calculateDurationMinutes, formatDuration, toLocalDatetimeLocalString } from "@/shared/lib";
import type { ProjectOption, Session } from "../model";

interface SessionEditFormProps {
	session: Session;
	projects: ProjectOption[];
	onSave: (sessionId: string, startTime: string, endTime: string, projectId: string) => void;
	onCancel: () => void;
}

export function SessionEditForm({ session, projects, onSave, onCancel }: SessionEditFormProps) {
	const [editStartTime, setEditStartTime] = useState(session.startTime);
	const [editEndTime, setEditEndTime] = useState(session.endTime);
	const [editProjectId, setEditProjectId] = useState(session.projectId);

	const handleSave = () => {
		onSave(session.id, editStartTime, editEndTime, editProjectId);
	};

	return (
		<div className="rounded-lg border border-border/80 bg-card shadow-soft p-5 space-y-4">
			<div>
				<label className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5">
					Project
				</label>
				<select
					value={editProjectId}
					onChange={(e) => setEditProjectId(e.target.value)}
					className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
				>
					{projects.map((p) => (
						<option key={p.id} value={p.id}>
							{p.name}
						</option>
					))}
				</select>
			</div>
			<div>
				<label className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5">
					Start
				</label>
				<input
					type="datetime-local"
					value={toLocalDatetimeLocalString(new Date(editStartTime))}
					onChange={(e) => setEditStartTime(new Date(e.target.value).toISOString())}
					className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
				/>
			</div>
			<div>
				<label className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5">
					End
				</label>
				<input
					type="datetime-local"
					value={toLocalDatetimeLocalString(new Date(editEndTime))}
					onChange={(e) => setEditEndTime(new Date(e.target.value).toISOString())}
					className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
				/>
			</div>
			<div className="rounded-md bg-secondary/50 px-3 py-2.5">
				<p className="text-muted-foreground text-sm">
					Duration{" "}
					<span className="font-medium text-foreground tabular-nums">
						{formatDuration(calculateDurationMinutes(editStartTime, editEndTime))}
					</span>
				</p>
			</div>
			<div className="flex gap-2 pt-1">
				<button
					onClick={handleSave}
					className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-base font-medium bg-accent text-accent-foreground hover:bg-accent/90 transition-colors duration-150"
				>
					<Save className="w-4 h-4" />
					Save
				</button>
				<button
					onClick={onCancel}
					className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-base font-medium border border-border text-foreground hover:bg-secondary/60 transition-colors duration-150"
				>
					<X className="w-4 h-4" />
					Cancel
				</button>
			</div>
		</div>
	);
}
