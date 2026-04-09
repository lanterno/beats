/**
 * Timer Manager Component
 * Main timer UI with project selection and start/stop controls.
 */

import { Calendar, Play, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import type { ProjectWithDuration } from "@/entities/project";
import { cn, parseUtcIso, toLocalDatetimeLocalString } from "@/shared/lib";
import { useTimer } from "../model";
import { ProjectSelector } from "./ProjectSelector";
import { TimerDisplay } from "./TimerDisplay";

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

	// Pre-select project when arriving from project page
	useEffect(() => {
		if (initialProjectId && projects.some((p) => p.id === initialProjectId)) {
			selectProject(initialProjectId);
		}
	}, [initialProjectId, projects, selectProject]);

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

		if (projectName) {
			toast.success(`Logged ${minutes}m to ${projectName}`);
			onSessionSaved?.();
		}
	};

	return (
		<div
			className={cn(
				"relative rounded-lg border bg-card shadow-soft p-6 h-full flex flex-col",
				isRunning ? "border-accent/30 shadow-glow-amber" : "border-border",
			)}
		>
			<div className="relative mb-4">
				<ProjectSelector
					projects={projects}
					selectedProjectId={selectedProjectId}
					onSelect={selectProject}
					disabled={isRunning}
				/>
			</div>

			<div className="flex flex-col flex-1 justify-between border-t border-border/50 pt-5 mt-1">
				<TimerDisplay
					elapsedSeconds={elapsedSeconds}
					customStartTime={customStartTime}
					isRunning={isRunning}
					projectName={selectedProject?.name}
				/>

				<div className="space-y-2">
					<div className="flex gap-2">
						<button
							onClick={handleStart}
							disabled={!selectedProjectId || isRunning}
							className={cn(
								"flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-base font-medium transition-colors",
								isRunning || !selectedProjectId
									? "bg-muted text-muted-foreground cursor-not-allowed"
									: "bg-accent text-accent-foreground hover:bg-accent/90",
							)}
						>
							<Play className="w-4 h-4" />
							Start
						</button>

						<button
							onClick={handleStop}
							disabled={!isRunning}
							className={cn(
								"flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-base font-medium transition-colors",
								!isRunning
									? "bg-muted text-muted-foreground cursor-not-allowed"
									: "bg-destructive text-destructive-foreground hover:opacity-90",
							)}
						>
							<Square className="w-4 h-4" />
							Stop
						</button>
					</div>

					{selectedProjectId && !isRunning && (
						<button
							onClick={() => setShowStartTimeInput(!showStartTimeInput)}
							className="w-full flex items-center justify-center gap-2 py-2 rounded-md text-sm text-muted-foreground hover:text-accent hover:bg-accent/5 transition-colors duration-150"
						>
							<Calendar className="w-3.5 h-3.5" />
							{showStartTimeInput ? "Hide start time" : "Set start time"}
						</button>
					)}

					{isRunning && (
						<button
							onClick={() => setShowStopTimeInput(!showStopTimeInput)}
							className="w-full flex items-center justify-center gap-2 py-2 rounded-md text-sm text-muted-foreground hover:text-accent hover:bg-accent/5 transition-colors duration-150"
						>
							<Calendar className="w-3.5 h-3.5" />
							{showStopTimeInput ? "Hide stop time" : "Set stop time"}
						</button>
					)}
				</div>
			</div>

			{showStartTimeInput && !isRunning && (
				<div className="mt-4 pt-4 border-t border-border/60">
					<label className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-2">
						Start time
					</label>
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
						className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
					/>
				</div>
			)}

			{showStopTimeInput && isRunning && (
				<div className="mt-4 pt-4 border-t border-border/60">
					<label className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-2">
						Stop time
					</label>
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
						className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
					/>
				</div>
			)}

			{isRunning && (
				<div className="absolute top-5 right-5 flex items-center gap-2 rounded-full bg-accent-gold/15 px-3 py-1.5 border border-accent-gold/20">
					<span className="w-1.5 h-1.5 rounded-full bg-accent-gold animate-pulse" />
					<span className="text-accent-gold text-xs uppercase tracking-[0.12em] font-medium">
						Running
					</span>
				</div>
			)}
		</div>
	);
}
