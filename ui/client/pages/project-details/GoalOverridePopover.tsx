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
		note: string;
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
	const [note, setNote] = useState("");
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
			onSave({ weeklyGoal: null, goalType, scope, note });
			return;
		}
		const val = Number.parseFloat(hours);
		if (Number.isNaN(val) || val <= 0) return;
		onSave({ weeklyGoal: val, goalType, scope, note });
	};

	return (
		<div
			ref={ref}
			className="absolute z-50 right-0 top-full mt-1 rounded-lg border border-border bg-popover shadow-card p-3 w-56"
			style={{ animation: "fadeSlideIn 100ms ease-out both" }}
		>
			<div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
				Override goal
			</div>

			{/* Has goal / No goal toggle */}
			<div className="flex gap-1 mb-2">
				<button
					onClick={() => setNoGoal(false)}
					className={`flex-1 text-[10px] py-1 rounded transition-colors ${
						!noGoal
							? "bg-accent text-accent-foreground"
							: "bg-secondary/50 text-muted-foreground hover:text-foreground"
					}`}
				>
					Has goal
				</button>
				<button
					onClick={() => setNoGoal(true)}
					className={`flex-1 text-[10px] py-1 rounded transition-colors ${
						noGoal
							? "bg-accent text-accent-foreground"
							: "bg-secondary/50 text-muted-foreground hover:text-foreground"
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
							className="w-20 text-sm font-mono bg-secondary/50 border border-border rounded px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
						/>
						<span className="text-xs text-muted-foreground">h/week</span>
					</div>

					<div className="flex gap-1 mb-2">
						<button
							onClick={() => setGoalType("target")}
							className={`flex-1 text-[10px] py-1 rounded transition-colors ${
								goalType === "target"
									? "bg-accent text-accent-foreground"
									: "bg-secondary/50 text-muted-foreground hover:text-foreground"
							}`}
						>
							Target
						</button>
						<button
							onClick={() => setGoalType("cap")}
							className={`flex-1 text-[10px] py-1 rounded transition-colors ${
								goalType === "cap"
									? "bg-accent text-accent-foreground"
									: "bg-secondary/50 text-muted-foreground hover:text-foreground"
							}`}
						>
							Cap
						</button>
					</div>
				</>
			)}

			{/* Scope selector */}
			<div className="flex gap-1 mb-2">
				<button
					onClick={() => setScope("week")}
					className={`flex-1 text-[10px] py-1 rounded transition-colors ${
						scope === "week"
							? "bg-accent text-accent-foreground"
							: "bg-secondary/50 text-muted-foreground hover:text-foreground"
					}`}
				>
					This week only
				</button>
				<button
					onClick={() => setScope("permanent")}
					className={`flex-1 text-[10px] py-1 rounded transition-colors ${
						scope === "permanent"
							? "bg-accent text-accent-foreground"
							: "bg-secondary/50 text-muted-foreground hover:text-foreground"
					}`}
				>
					From here on
				</button>
			</div>

			<input
				type="text"
				value={note}
				onChange={(e) => setNote(e.target.value)}
				onKeyDown={(e) => {
					if (e.key === "Enter") handleSave();
					if (e.key === "Escape") onClose();
				}}
				placeholder="Reason (optional)"
				className="w-full text-xs bg-secondary/50 border border-border rounded px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-accent mb-2"
			/>

			<div className="flex gap-1">
				<button
					onClick={handleSave}
					className="flex-1 px-2 py-1 text-[10px] font-medium rounded bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
				>
					{noGoal ? "Save (no goal)" : "Save"}
				</button>
				{hasExistingOverride && (
					<button
						onClick={onRemove}
						className="px-2 py-1 text-[10px] font-medium rounded bg-destructive/15 text-destructive hover:bg-destructive/25 transition-colors"
					>
						Remove
					</button>
				)}
			</div>
		</div>
	);
}
