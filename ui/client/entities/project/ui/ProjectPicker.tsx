/**
 * ProjectPicker — the one project-choice primitive.
 *
 * Replaces the seven ad-hoc project pickers across the app (native <select>s
 * in SidebarTimer / QuickLog / TodaysPlan / RecurringIntentions / Insights
 * filter, the bespoke ProjectSelector on the homepage). Every consumer gets
 * the same search, archive filtering, recents-on-top, keyboard nav, and
 * color context for free.
 *
 * a11y:
 * - Trigger is a real <button> with aria-haspopup=listbox + aria-expanded.
 * - Search input has role=combobox, aria-expanded, aria-controls (the
 *   listbox id), and aria-activedescendant pointing at the highlighted
 *   option id — focus stays on the input while arrow keys move the
 *   highlight visually.
 * - List has role=listbox; items have role=option + aria-selected.
 * - ArrowDown/Up move highlight; Enter selects; Escape closes.
 *
 * P2.1 of the project-management revamp.
 */

import { Check, ChevronDown, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useAuth } from "@/features/auth";
import { cn, formatDuration } from "@/shared/lib";
import type { ProjectWithDuration } from "../model";
import {
	filterAndRankProjects,
	readPickerRecents,
	recordPickerRecent,
	type SearchField,
} from "../model";

export interface ProjectPickerProps {
	value: string | null;
	onChange: (projectId: string | null) => void;
	projects: ProjectWithDuration[];
	/** Default false — archived projects hidden via the shared visibility filter. */
	showArchived?: boolean;
	/** Show weekly minutes alongside each item (used for picker rows that
	 *  benefit from "X is at 4h/10h this week" context). Default false. */
	showContext?: boolean;
	/** Surface most-recently-selected projects at the top with no query. Default true. */
	recencyBoost?: boolean;
	/** Substring-match against these fields. Default ['name', 'description']. */
	searchFields?: SearchField[];
	/** Placeholder for the trigger when nothing is selected. */
	triggerPlaceholder?: string;
	/** Placeholder for the search input. */
	searchPlaceholder?: string;
	/** Compact trigger variant (sidebar / inline use). */
	compact?: boolean;
	/** Disable the entire picker (e.g. timer running). */
	disabled?: boolean;
	/** Extra trigger className passthrough. */
	className?: string;
	/** Accessible label override for the trigger (defaults to "Project"). */
	ariaLabel?: string;
}

export function ProjectPicker({
	value,
	onChange,
	projects,
	showArchived = false,
	showContext = false,
	recencyBoost = true,
	searchFields,
	triggerPlaceholder = "Select project…",
	searchPlaceholder = "Search projects…",
	compact = false,
	disabled = false,
	className,
	ariaLabel = "Project",
}: ProjectPickerProps) {
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState("");
	const [highlight, setHighlight] = useState(0);
	const listboxId = useId();
	const optionId = (id: string) => `${listboxId}-${id}`;

	const containerRef = useRef<HTMLDivElement>(null);
	const inputRef = useRef<HTMLInputElement>(null);
	const listRef = useRef<HTMLUListElement>(null);
	const { user } = useAuth();
	const userKey = user?.email ?? null;

	// Read recents only when the picker opens — avoids re-reading on every
	// keystroke and keeps the closed picker side-effect-free.
	const recents = useMemo(
		() => (open && recencyBoost ? readPickerRecents(userKey) : []),
		[open, recencyBoost, userKey],
	);

	const items = useMemo(
		() =>
			filterAndRankProjects(projects, query, {
				showArchived,
				searchFields,
				recents,
			}),
		[projects, query, showArchived, searchFields, recents],
	);

	const selectedProject = projects.find((p) => p.id === value) ?? null;

	useEffect(() => {
		// Clamp highlight whenever the items list shrinks.
		setHighlight((h) => (items.length === 0 ? 0 : Math.min(h, items.length - 1)));
	}, [items.length]);

	useEffect(() => {
		if (!open) return;
		const onDown = (e: MouseEvent) => {
			if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
				setOpen(false);
			}
		};
		document.addEventListener("mousedown", onDown);
		return () => document.removeEventListener("mousedown", onDown);
	}, [open]);

	useEffect(() => {
		if (open) {
			// Focus the search input the tick after open so it's reliably mounted.
			const id = requestAnimationFrame(() => inputRef.current?.focus());
			return () => cancelAnimationFrame(id);
		}
	}, [open]);

	// Keep the highlighted option in view as the user arrow-keys through the
	// list. With more than ~7 projects, the previous behavior left the
	// aria-activedescendant pointing off-screen, breaking the WAI-ARIA
	// combobox contract for keyboard + screen reader users.
	const activeOptionId = items[highlight]?.id ? optionId(items[highlight].id) : null;
	useEffect(() => {
		if (!open || !activeOptionId || !listRef.current) return;
		const node = listRef.current.querySelector<HTMLLIElement>(
			`[id="${CSS.escape(activeOptionId)}"]`,
		);
		// jsdom doesn't implement scrollIntoView; the type-guard keeps both
		// runtimes happy without leaking a test-only branch.
		if (node && typeof node.scrollIntoView === "function") {
			node.scrollIntoView({ block: "nearest" });
		}
	}, [open, activeOptionId]);

	const handleSelect = (projectId: string) => {
		onChange(projectId);
		if (recencyBoost) recordPickerRecent(userKey, projectId);
		setOpen(false);
		setQuery("");
		setHighlight(0);
	};

	const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
		if (e.key === "ArrowDown") {
			e.preventDefault();
			setHighlight((h) => (items.length === 0 ? 0 : Math.min(items.length - 1, h + 1)));
		} else if (e.key === "ArrowUp") {
			e.preventDefault();
			setHighlight((h) => Math.max(0, h - 1));
		} else if (e.key === "Enter") {
			const item = items[highlight];
			if (item) {
				e.preventDefault();
				handleSelect(item.id);
			}
		} else if (e.key === "Escape") {
			e.preventDefault();
			setOpen(false);
		}
	};

	const activeId = activeOptionId ?? undefined;

	// Reflect the selection in the trigger's accessible name. Before this,
	// the trigger always announced just "Project, button" regardless of what
	// was chosen, so AT users had no way to tell what the picker held.
	const triggerAriaLabel = selectedProject
		? `${ariaLabel}: ${selectedProject.name}${selectedProject.archived ? " (archived)" : ""}`
		: ariaLabel;

	return (
		<div ref={containerRef} className={cn("relative", className)}>
			<button
				type="button"
				onClick={() => setOpen((o) => !o)}
				aria-haspopup="listbox"
				aria-expanded={open}
				aria-label={triggerAriaLabel}
				disabled={disabled}
				className={cn(
					"w-full inline-flex items-center gap-2 rounded-md border border-input bg-background text-left text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
					compact ? "min-h-9 px-3 text-sm" : "min-h-10 px-3 text-base",
					"hover:bg-secondary/40 disabled:opacity-50 disabled:cursor-not-allowed",
				)}
			>
				{selectedProject ? (
					<>
						<span
							className="inline-block w-2 h-2 rounded-full shrink-0"
							style={{ backgroundColor: selectedProject.color }}
							aria-hidden="true"
						/>
						<span className="truncate flex-1 min-w-0">{selectedProject.name}</span>
						{selectedProject.archived && (
							<span className="text-[9px] uppercase tracking-wider px-1 py-0.5 rounded border border-muted-foreground/30 text-muted-foreground shrink-0">
								Archived
							</span>
						)}
					</>
				) : (
					<span className="flex-1 min-w-0 text-muted-foreground/60">{triggerPlaceholder}</span>
				)}
				<ChevronDown
					className={cn(
						"w-3.5 h-3.5 text-muted-foreground/60 shrink-0 transition-transform",
						open && "rotate-180",
					)}
					aria-hidden="true"
				/>
			</button>

			{open && (
				<div className="absolute z-50 mt-1 w-full min-w-56 rounded-lg border border-border bg-popover shadow-card overflow-hidden">
					<div className="relative border-b border-border/60">
						<Search
							className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/60 pointer-events-none"
							aria-hidden="true"
						/>
						<input
							ref={inputRef}
							type="text"
							role="combobox"
							aria-expanded={open}
							aria-controls={listboxId}
							aria-activedescendant={activeId}
							aria-autocomplete="list"
							value={query}
							onChange={(e) => {
								setQuery(e.target.value);
								setHighlight(0);
							}}
							onKeyDown={handleKeyDown}
							placeholder={searchPlaceholder}
							className="w-full bg-transparent py-2 pl-9 pr-8 text-sm text-foreground placeholder:text-muted-foreground/50 focus-visible:outline-hidden"
						/>
						{query !== "" && (
							<button
								type="button"
								onClick={() => {
									setQuery("");
									setHighlight(0);
									inputRef.current?.focus();
								}}
								aria-label="Clear search"
								className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-muted-foreground/50 hover:text-foreground hover:bg-secondary/40"
							>
								<X className="w-3 h-3" />
							</button>
						)}
					</div>
					<ul
						ref={listRef}
						id={listboxId}
						role="listbox"
						aria-label={ariaLabel}
						className="max-h-64 overflow-y-auto py-1"
					>
						{items.length === 0 ? (
							<li className="px-3 py-2 text-sm text-muted-foreground/60">No projects match</li>
						) : (
							items.map((p, i) => {
								const isHighlighted = i === highlight;
								const isSelected = p.id === value;
								return (
									<li
										key={p.id}
										id={optionId(p.id)}
										role="option"
										aria-selected={isSelected}
										onClick={() => handleSelect(p.id)}
										onMouseEnter={() => setHighlight(i)}
										className={cn(
											"flex items-center gap-2 px-3 py-2 text-sm cursor-pointer transition-colors",
											isHighlighted ? "bg-accent/15 text-foreground" : "text-foreground/90",
										)}
									>
										<span
											className="inline-block w-2 h-2 rounded-full shrink-0"
											style={{ backgroundColor: p.color }}
											aria-hidden="true"
										/>
										<span className="truncate flex-1 min-w-0">{p.name}</span>
										{p.archived && (
											<span className="text-[9px] uppercase tracking-wider px-1 py-0.5 rounded border border-muted-foreground/30 text-muted-foreground shrink-0">
												Archived
											</span>
										)}
										{showContext && p.weeklyMinutes > 0 && (
											<span className="text-[11px] tabular-nums text-muted-foreground shrink-0">
												{formatDuration(p.weeklyMinutes)}
											</span>
										)}
										{isSelected && (
											<Check className="w-3.5 h-3.5 text-accent shrink-0" aria-hidden="true" />
										)}
									</li>
								);
							})
						)}
					</ul>
				</div>
			)}
		</div>
	);
}
