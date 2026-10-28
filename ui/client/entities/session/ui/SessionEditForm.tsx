/**
 * Session Edit Form Component
 * Form for editing a work session: project, times, and the note (#348) —
 * the one free-text input in the app. On an organisation's project the
 * note is part of the organisation's record (rule 3), so the input itself
 * carries the marker saying who reads it, and the marker follows the
 * project picked: moving the session to a personal project makes the note
 * private again, and the line goes.
 */

import { Save, X } from "lucide-react";
import { useId, useState } from "react";
import {
	calculateDurationMinutes,
	formatDuration,
	isValidTimeRange,
	toLocalDatetimeLocalString,
} from "@/shared/lib";
import { Button } from "@/shared/ui";
import type { ProjectOption, Session } from "../model";

/** `.lbl` — the small-caps label, above its field. */
const LABEL =
	"block mb-1.5 font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";

/**
 * The form sits on the wash inside the day's panel, so its fields are the
 * panel again (panel-on-panel): no border, the accent's ring on focus.
 */
const FIELD =
	"w-full rounded-xl bg-card px-3 py-2 text-[13.5px] text-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent";

interface SessionEditFormProps {
	session: Session;
	projects: ProjectOption[];
	onSave: (
		sessionId: string,
		startTime: string,
		endTime: string,
		projectId: string,
		note: string,
	) => void;
	onCancel: () => void;
}

export function SessionEditForm({ session, projects, onSave, onCancel }: SessionEditFormProps) {
	const [editStartTime, setEditStartTime] = useState(session.startTime);
	const [editEndTime, setEditEndTime] = useState(session.endTime);
	const [editProjectId, setEditProjectId] = useState(session.projectId);
	const [editNote, setEditNote] = useState(session.note ?? "");

	const validRange = isValidTimeRange(editStartTime, editEndTime);
	const noteReader = projects.find((p) => p.id === editProjectId)?.organisation;

	const handleSave = () => {
		if (!validRange) return;
		onSave(session.id, editStartTime, editEndTime, editProjectId, editNote);
	};

	const fieldId = useId();

	return (
		<div className="rounded-[1.125rem] bg-secondary p-5 space-y-4">
			<div>
				<label htmlFor={`${fieldId}-project`} className={LABEL}>
					Project
				</label>
				<select
					id={`${fieldId}-project`}
					value={editProjectId}
					onChange={(e) => setEditProjectId(e.target.value)}
					className={`${FIELD} font-body font-medium`}
				>
					{projects.map((p) => (
						<option key={p.id} value={p.id}>
							{p.name}
						</option>
					))}
				</select>
			</div>
			<div>
				<label htmlFor={`${fieldId}-start`} className={LABEL}>
					Start
				</label>
				<input
					id={`${fieldId}-start`}
					type="datetime-local"
					value={toLocalDatetimeLocalString(new Date(editStartTime))}
					onChange={(e) => setEditStartTime(new Date(e.target.value).toISOString())}
					className={`${FIELD} font-mono font-bold`}
				/>
			</div>
			<div>
				<label htmlFor={`${fieldId}-end`} className={LABEL}>
					End
				</label>
				<input
					id={`${fieldId}-end`}
					type="datetime-local"
					value={toLocalDatetimeLocalString(new Date(editEndTime))}
					onChange={(e) => setEditEndTime(new Date(e.target.value).toISOString())}
					className={`${FIELD} font-mono font-bold`}
				/>
			</div>
			<div>
				<label htmlFor={`${fieldId}-note`} className={LABEL}>
					Note (optional)
				</label>
				<input
					id={`${fieldId}-note`}
					value={editNote}
					onChange={(e) => setEditNote(e.target.value)}
					maxLength={2000}
					placeholder="What this session was"
					aria-describedby={noteReader ? `${fieldId}-note-reader` : undefined}
					className={FIELD}
				/>
				{noteReader && (
					<p
						id={`${fieldId}-note-reader`}
						className="mt-1 text-[10.5px] font-medium text-muted-foreground"
					>
						{noteReader} can read this note
					</p>
				)}
			</div>
			<div className="rounded-xl bg-card px-3 py-2.5">
				<p className="text-muted-foreground text-[13px] font-medium">
					Duration{" "}
					<span className="font-mono font-bold text-foreground">
						{formatDuration(calculateDurationMinutes(editStartTime, editEndTime))}
					</span>
				</p>
			</div>
			{!validRange && (
				<p className="text-[13px] font-medium text-destructive-ink" role="alert">
					End time must be after the start time.
				</p>
			)}
			<div className="flex gap-2 pt-1">
				<Button onClick={handleSave} disabled={!validRange} className="flex-1">
					<Save />
					Save
				</Button>
				<Button variant="secondary" onClick={onCancel} className="flex-1">
					<X />
					Cancel
				</Button>
			</div>
		</div>
	);
}
