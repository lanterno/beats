/**
 * Timer Manager Component
 * Main timer UI with project selection and start/stop controls.
 */

import { Calendar, Play, Square } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { toast } from "sonner";
import { ProjectPicker, type ProjectWithDuration, readPickerRecents } from "@/entities/project";
import { useAuth } from "@/features/auth";
import { cn, parseUtcIso, toLocalDatetimeLocalString } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { fetchDailyAverage } from "../api";
import { useTimer } from "../model";
import { TimerDisplay } from "./TimerDisplay";

/** `.lbl` — the small-caps label. */
const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";

/** Start and Stop: pills, as the sidebar timer's. */
const PILL =
	"flex-1 flex items-center justify-center gap-2 py-2.5 rounded-full text-sm font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

const TOGGLE =
	"w-full flex items-center justify-center gap-2 py-2 rounded-full text-[13px] font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors duration-150 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** The mockup's `.dlg input`: a wash, no border, the figures face. */
const FIELD =
	"w-full rounded-xl bg-secondary px-3 py-2 text-[13.5px] font-mono font-bold text-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent";

interface TimerManagerProps {
	projects: ProjectWithDuration[];
	onSessionSaved?: () => void;
	initialProjectId?: string;
}

export function TimerManager({ projects, onSessionSaved, initialProjectId }: TimerManagerProps) {
	const {
		isRunning,
		selectedProjectId,
		elapsedSeconds,
		startTimer,
		stopTimer,
		selectProject,
		customStartTime,
		setCustomStartTime,
	} = useTimer();

	const [showStartTimeInput, setShowStartTimeInput] = useState(false);
	const [showStopTimeInput, setShowStopTimeInput] = useState(false);
	const [customStopTime, setCustomStopTime] = useState<string | null>(null);
	const { user } = useAuth();

	// Pre-select project: explicit initialProjectId takes precedence, else
	// fall back to the user's most-recently-selected project from
	// pickerRecents (P2.2 closes the "no default selection on timer mount"
	// gap with one line of glue).
	useEffect(() => {
		if (selectedProjectId) return;
		if (initialProjectId && projects.some((p) => p.id === initialProjectId)) {
			selectProject(initialProjectId);
			return;
		}
		const recents = readPickerRecents(user?.email ?? null);
		const lastUsed = recents.find((id) => projects.some((p) => p.id === id && !p.archived));
		if (lastUsed) selectProject(lastUsed);
	}, [initialProjectId, projects, selectProject, selectedProjectId, user?.email]);

	const selectedProject = projects.find((p) => p.id === selectedProjectId);

	const handleStart = () => {
		if (selectedProjectId) {
			if (showStartTimeInput && customStartTime) {
				startTimer(selectedProjectId, customStartTime);
			} else {
				startTimer(selectedProjectId);
			}
			setShowStartTimeInput(false);
		}
	};

	const handleStop = () => {
		const projectId = selectedProjectId;
		const projectName = selectedProject?.name;
		const stopTime = showStopTimeInput && customStopTime ? customStopTime : undefined;
		const endDate = stopTime ? new Date(stopTime) : new Date();

		let minutes = Math.floor(elapsedSeconds / 60);

		if (customStartTime) {
			const startDate = parseUtcIso(customStartTime);
			minutes = Math.floor((endDate.getTime() - startDate.getTime()) / 1000 / 60);
		}

		stopTimer(stopTime);
		setShowStartTimeInput(false);
		setShowStopTimeInput(false);
		setCustomStartTime(null);
		setCustomStopTime(null);

		if (projectName && projectId) {
			// Show immediate toast, then enhance with daily average
			fetchDailyAverage(projectId)
				.then(({ avg_minutes, days_tracked }) => {
					if (days_tracked > 0 && avg_minutes > 0) {
						const diff = minutes - avg_minutes;
						const pct = Math.round((Math.abs(diff) / avg_minutes) * 100);
						const comparison =
							diff > 0
								? `${pct}% above your daily avg (${avg_minutes}m)`
								: diff < 0
									? `${pct}% below your daily avg (${avg_minutes}m)`
									: `right at your daily avg`;
						toast.success(`Logged ${minutes}m to ${projectName} — ${comparison}`);
					} else {
						toast.success(`Logged ${minutes}m to ${projectName}`);
					}
				})
				.catch(() => {
					toast.success(`Logged ${minutes}m to ${projectName}`);
				});
			onSessionSaved?.();
		}
	};

	const fieldId = useId();

	return (
		<Panel className="relative h-full flex flex-col">
			<div className="relative mb-4">
				<p className={cn(LABEL, "mb-2")}>Project</p>
				<ProjectPicker
					projects={projects}
					value={selectedProjectId}
					onChange={selectProject}
					disabled={isRunning}
					showContext
					ariaLabel="Project"
				/>
			</div>

			<div className="flex flex-col flex-1 justify-between border-t border-border pt-5 mt-1">
				<TimerDisplay
					elapsedSeconds={elapsedSeconds}
					customStartTime={customStartTime}
					isRunning={isRunning}
					projectName={selectedProject?.name}
				/>

				<div className="space-y-2">
					<div className="flex gap-2">
						<button
							type="button"
							onClick={handleStart}
							disabled={!selectedProjectId || isRunning}
							className={cn(
								PILL,
								// Idle, Start is the wash; the accent is the running timer's alone.
								isRunning || !selectedProjectId
									? "bg-sidebar-accent text-muted-foreground cursor-not-allowed"
									: "bg-sidebar-accent text-foreground hover:bg-[color-mix(in_srgb,var(--color-sidebar-accent),var(--color-foreground)_8%)]",
							)}
						>
							<Play className="w-4 h-4" />
							Start
						</button>

						<button
							type="button"
							onClick={handleStop}
							disabled={!isRunning}
							className={cn(
								PILL,
								!isRunning
									? "bg-sidebar-accent text-muted-foreground cursor-not-allowed"
									: "bg-accent text-accent-foreground hover:bg-accent/90",
							)}
						>
							<Square className="w-4 h-4" />
							Stop
						</button>
					</div>

					{selectedProjectId && !isRunning && (
						<button
							type="button"
							onClick={() => setShowStartTimeInput(!showStartTimeInput)}
							className={TOGGLE}
						>
							<Calendar className="w-3.5 h-3.5" />
							{showStartTimeInput ? "Hide start time" : "Set start time"}
						</button>
					)}

					{isRunning && (
						<button
							type="button"
							onClick={() => setShowStopTimeInput(!showStopTimeInput)}
							className={TOGGLE}
						>
							<Calendar className="w-3.5 h-3.5" />
							{showStopTimeInput ? "Hide stop time" : "Set stop time"}
						</button>
					)}
				</div>
			</div>

			{showStartTimeInput && !isRunning && (
				<div className="mt-4 pt-4 border-t border-border">
					<label htmlFor={`${fieldId}-start`} className={cn(LABEL, "block mb-2")}>
						Start time
					</label>
					<input
						id={`${fieldId}-start`}
						type="datetime-local"
						value={
							customStartTime
								? toLocalDatetimeLocalString(new Date(customStartTime))
								: toLocalDatetimeLocalString(new Date(Date.now() - 60 * 60 * 1000))
						}
						onChange={(e) => {
							const date = new Date(e.target.value);
							setCustomStartTime(date.toISOString());
						}}
						className={FIELD}
					/>
				</div>
			)}

			{showStopTimeInput && isRunning && (
				<div className="mt-4 pt-4 border-t border-border">
					<label htmlFor={`${fieldId}-stop`} className={cn(LABEL, "block mb-2")}>
						Stop time
					</label>
					<input
						id={`${fieldId}-stop`}
						type="datetime-local"
						value={
							customStopTime
								? toLocalDatetimeLocalString(new Date(customStopTime))
								: toLocalDatetimeLocalString(new Date())
						}
						onChange={(e) => {
							const date = new Date(e.target.value);
							setCustomStopTime(date.toISOString());
						}}
						className={FIELD}
					/>
				</div>
			)}

			{isRunning && (
				<div className="absolute top-5 right-5 flex items-center gap-2 rounded-full bg-accent px-3 py-1">
					<span className="w-1.5 h-1.5 rounded-full bg-accent-foreground animate-pulse" />
					<span className="text-accent-foreground text-[10.5px] uppercase tracking-[0.14em] font-bold">
						Running
					</span>
				</div>
			)}
		</Panel>
	);
}
