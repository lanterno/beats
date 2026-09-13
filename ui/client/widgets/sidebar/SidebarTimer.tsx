/**
 * Sidebar Timer Component
 * Vertical timer card with prominent display and full-width controls.
 * A wash block, as in the mockup's `.timer`: the elapsed figure in the
 * display face, the primary action an accent pill, idle in the wash.
 */

import { Calendar, Play, Square } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ProjectPicker, type ProjectWithDuration } from "@/entities/project";
import {
	cn,
	formatDuration,
	formatSecondsToTime,
	parseUtcIso,
	toLocalDatetimeLocalString,
} from "@/shared/lib";
import { AnimatedDigits } from "@/shared/ui";

export interface TimerProps {
	projects: ProjectWithDuration[];
	isRunning: boolean;
	selectedProjectId: string | null;
	elapsedSeconds: number;
	customStartTime: string | null;
	startTimer: (projectId: string, startTime?: string) => void;
	stopTimer: (customStopTime?: string) => void;
	selectProject: (projectId: string | null) => void;
	setCustomStartTime: (startTime: string | null) => void;
}

const PILL =
	"w-full inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

const TOGGLE =
	"inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors";

// The mockup's `.dlg input`: a wash, no border, the figures face.
const FIELD =
	"w-full rounded-md bg-secondary px-3 py-2 text-[13.5px] font-mono font-bold text-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent";

export function SidebarTimer({
	projects,
	isRunning,
	selectedProjectId,
	elapsedSeconds,
	customStartTime,
	startTimer,
	stopTimer,
	selectProject,
	setCustomStartTime,
}: TimerProps) {
	const [showStartTimeInput, setShowStartTimeInput] = useState(false);
	const [showStopTimeInput, setShowStopTimeInput] = useState(false);
	const [customStopTime, setCustomStopTime] = useState<string | null>(null);

	const selectedProject = projects.find((p) => p.id === selectedProjectId);

	let totalSeconds = elapsedSeconds;
	if (customStartTime && isRunning) {
		const startDate = parseUtcIso(customStartTime);
		const now = new Date();
		totalSeconds = Math.floor((now.getTime() - startDate.getTime()) / 1000);
	}

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
		const project = selectedProject;
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
		if (project) {
			toast(
				<div className="flex items-center gap-2.5">
					<div
						className="w-2.5 h-2.5 rounded-full shrink-0"
						style={{ backgroundColor: project.color }}
					/>
					<div className="min-w-0">
						<p className="text-sm font-medium text-foreground">
							{formatDuration(minutes)}{" "}
							<span className="text-muted-foreground font-normal">logged to</span> {project.name}
						</p>
					</div>
				</div>,
			);
		}
	};

	return (
		<div className="rounded-[1.375rem] bg-secondary px-3 pt-4 pb-3.5 transition-colors duration-300">
			{/* Timer display */}
			<div className="text-center mb-3">
				<AnimatedDigits
					value={formatSecondsToTime(totalSeconds)}
					className={cn(
						"font-heading text-3xl font-extrabold tracking-[-0.01em] leading-none",
						isRunning ? "text-foreground" : "text-muted-foreground",
					)}
				/>
				{isRunning && selectedProject && (
					<div className="flex items-center justify-center gap-1.5 mt-1.5">
						<span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
						<div
							className="w-2 h-2 rounded-full shrink-0"
							style={{ backgroundColor: selectedProject.color }}
						/>
						<span className="text-muted-foreground text-[12.5px] font-medium truncate max-w-[140px]">
							{selectedProject.name}
						</span>
					</div>
				)}
			</div>

			{/* Project picker (when not running). Archived projects are filtered
			    via the shared selector inside ProjectPicker; the running timer
			    keeps showing its project even if it gets archived mid-session
			    (selectedProject lookup above is unfiltered). */}
			{!isRunning && (
				<div className="mb-3">
					<ProjectPicker
						projects={projects}
						value={selectedProjectId}
						onChange={selectProject}
						compact
						ariaLabel="Timer project"
					/>
				</div>
			)}

			{/* Action button */}
			{isRunning ? (
				<div className="space-y-2">
					<button
						type="button"
						onClick={handleStop}
						className={cn(PILL, "bg-accent text-accent-foreground hover:bg-accent/90")}
					>
						<Square className="w-3 h-3" fill="currentColor" />
						Stop
					</button>

					<div className="flex items-center justify-center">
						<button
							type="button"
							onClick={() => {
								setShowStopTimeInput(!showStopTimeInput);
								if (!showStopTimeInput && !customStopTime) {
									setCustomStopTime(new Date().toISOString());
								}
							}}
							className={cn(TOGGLE, showStopTimeInput && "bg-sidebar-accent text-foreground")}
						>
							<Calendar className="w-3 h-3" />
							Custom stop
						</button>
					</div>

					{showStopTimeInput && (
						<input
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
					)}
				</div>
			) : (
				<div className="space-y-2">
					<button
						type="button"
						onClick={handleStart}
						disabled={!selectedProjectId}
						className={cn(
							PILL,
							// The mockup's `.timer.idle .btn`: the wash, so the accent
							// pill is the running state alone.
							!selectedProjectId
								? "bg-sidebar-accent text-muted-foreground cursor-not-allowed"
								: "bg-sidebar-accent text-foreground hover:bg-[color-mix(in_srgb,var(--color-sidebar-accent),var(--color-foreground)_8%)]",
						)}
					>
						<Play className="w-3 h-3" fill="currentColor" />
						Start
					</button>

					{selectedProjectId && (
						<div className="flex items-center justify-center">
							<button
								type="button"
								onClick={() => {
									setShowStartTimeInput(!showStartTimeInput);
									if (!showStartTimeInput && !customStartTime) {
										setCustomStartTime(new Date(Date.now() - 60 * 60 * 1000).toISOString());
									}
								}}
								className={cn(TOGGLE, showStartTimeInput && "bg-sidebar-accent text-foreground")}
							>
								<Calendar className="w-3 h-3" />
								Custom start
							</button>
						</div>
					)}

					{showStartTimeInput && (
						<input
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
					)}
				</div>
			)}
		</div>
	);
}
