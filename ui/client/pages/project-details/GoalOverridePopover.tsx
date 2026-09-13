/**
 * GoalOverridePopover — inline editor for per-week goal overrides.
 * Opens when user clicks a goal value in the week history table.
 */
import { useEffect, useRef, useState } from "react";

interface GoalOverridePopoverProps {
	/** Current effective goal for this week; null when no goal applies */
	currentGoal: number | null;
	/** Current goal type */
	currentGoalType: "target" | "cap";
	/** Whether an override already exists for this week */
	hasExistingOverride: boolean;
	/** True when the existing override for this scope is itself a null-goal override */
	existingOverrideIsNull?: boolean;
	/** Called with the new override values */
	onSave: (values: {
		weeklyGoal: number | null;
		goalType: "target" | "cap";
		scope: "week" | "permanent";
	}) => void;
	/** Called to remove existing override */
	onRemove: () => void;
	onClose: () => void;
}

export function GoalOverridePopover({
	currentGoal,
	currentGoalType,
	hasExistingOverride,
	existingOverrideIsNull = false,
	onSave,
	onRemove,
	onClose,
}: GoalOverridePopoverProps) {
	const [hours, setHours] = useState(currentGoal != null ? String(currentGoal) : "");
	const [goalType, setGoalType] = useState<"target" | "cap">(currentGoalType);
	const [scope, setScope] = useState<"week" | "permanent">("week");
	const [noGoal, setNoGoal] = useState(existingOverrideIsNull);
	const ref = useRef<HTMLDivElement>(null);
	const inputRef = useRef<HTMLInputElement>(null);

	useEffect(() => {
		if (!noGoal) inputRef.current?.select();
	}, [noGoal]);

	useEffect(() => {
		const handler = (e: MouseEvent) => {
			if (ref.current && !ref.current.contains(e.target as Node)) onClose();
		};
		document.addEventListener("mousedown", handler);
		return () => document.removeEventListener("mousedown", handler);
	}, [onClose]);

	const handleSave = () => {
		if (noGoal) {
			onSave({ weeklyGoal: null, goalType, scope });
			return;
		}
		const val = Number.parseFloat(hours);
		if (Number.isNaN(val) || val <= 0) return;
		onSave({ weeklyGoal: val, goalType, scope });
	};

	return (
		<div
			ref={ref}
			className="absolute z-50 right-0 top-full mt-1 rounded-2xl bg-popover shadow-card p-3 w-56"
			style={{ animation: "fadeSlideIn 100ms ease-out both" }}
		>
			<div className="font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-2">
				Override goal
			</div>

			{/* Has goal / No goal toggle */}
			<div className="flex gap-1 p-1 mb-2 rounded-full bg-secondary">
				<button
					type="button"
					onClick={() => setNoGoal(false)}
					className={`flex-1 text-[11px] font-bold py-1 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring ${
						!noGoal
							? "bg-accent text-accent-foreground"
							: "text-muted-foreground hover:text-foreground"
					}`}
				>
					Has goal
				</button>
				<button
					type="button"
					onClick={() => setNoGoal(true)}
					className={`flex-1 text-[11px] font-bold py-1 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring ${
						noGoal
							? "bg-accent text-accent-foreground"
							: "text-muted-foreground hover:text-foreground"
					}`}
				>
					No goal
				</button>
			</div>

			{/* Hours input + goal type (hidden when No goal) */}
			{!noGoal && (
				<>
					<div className="flex items-center gap-2 mb-2">
						<input
							ref={inputRef}
							type="number"
							min="0.5"
							step="0.5"
							value={hours}
							onChange={(e) => setHours(e.target.value)}
							onKeyDown={(e) => {
								if (e.key === "Enter") handleSave();
								if (e.key === "Escape") onClose();
							}}
							className="w-20 text-sm font-mono font-bold bg-secondary rounded-xl px-2.5 py-1 text-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent"
						/>
						<span className="text-xs text-muted-foreground">h/week</span>
					</div>

					<div className="flex gap-1 p-1 mb-2 rounded-full bg-secondary">
						<button
							type="button"
							onClick={() => setGoalType("target")}
							className={`flex-1 text-[11px] font-bold py-1 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring ${
								goalType === "target"
									? "bg-accent text-accent-foreground"
									: "text-muted-foreground hover:text-foreground"
							}`}
						>
							Target
						</button>
						<button
							type="button"
							onClick={() => setGoalType("cap")}
							className={`flex-1 text-[11px] font-bold py-1 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring ${
								goalType === "cap"
									? "bg-accent text-accent-foreground"
									: "text-muted-foreground hover:text-foreground"
							}`}
						>
							Cap
						</button>
					</div>
				</>
			)}

			{/* Scope selector. "Temporary shift" (renamed from "From here on")
			    is de-emphasized — for routine adjustments, editing the project's
			    DEFAULT weekly goal in Settings is the better path. P3.4 of the
			    project-management revamp. */}
			<div className="flex gap-1 p-1 mb-1 rounded-full bg-secondary">
				<button
					type="button"
					onClick={() => setScope("week")}
					className={`flex-1 text-[11px] font-bold py-1 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring ${
						scope === "week"
							? "bg-accent text-accent-foreground"
							: "text-muted-foreground hover:text-foreground"
					}`}
				>
					This week only
				</button>
				<button
					type="button"
					onClick={() => setScope("permanent")}
					title="Adds an override from this week forward. Prefer changing the project's default goal in Settings for routine adjustments."
					className={`flex-1 text-[11px] font-bold py-1 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring ${
						scope === "permanent"
							? "bg-accent text-accent-foreground"
							: "text-muted-foreground/70 hover:text-foreground"
					}`}
				>
					Temporary shift
				</button>
			</div>
			{scope === "permanent" && (
				<p className="text-[10px] text-muted-foreground/70 mb-2 leading-tight">
					For lasting changes, edit the default weekly goal in Settings.
				</p>
			)}

			<div className="flex gap-1">
				<button
					type="button"
					onClick={handleSave}
					className="flex-1 px-2 py-1.5 text-[11px] font-bold rounded-full bg-accent text-accent-foreground hover:bg-accent/90 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				>
					{noGoal ? "Save (no goal)" : "Save"}
				</button>
				{hasExistingOverride && (
					<button
						type="button"
						onClick={onRemove}
						className="px-3 py-1.5 text-[11px] font-bold rounded-full bg-destructive/15 text-destructive-ink hover:bg-destructive/25 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
					>
						Remove
					</button>
				)}
			</div>
		</div>
	);
}
