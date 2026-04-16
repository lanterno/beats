/**
 * Command Palette Component
 *
 * Presentational Cmd+K overlay. Callers pass the full list of available
 * commands via `items`; the palette handles fuzzy filtering, recency boosts,
 * keyboard navigation, and invocation. Each invocation is reported via
 * `onInvoke(item.id)` so the caller can record it in a recency store.
 */

import { Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn, fuzzyRank } from "@/shared/lib";

export interface CommandItem {
	id: string;
	label: string;
	/** Optional secondary text shown on the right (e.g. shortcut or path). */
	sublabel?: string;
	/** Keywords included in match text beyond `label`. */
	keywords?: string[];
	icon?: React.ReactNode;
	/** Project-style colored dot rendered in place of `icon`. */
	color?: string;
	action: () => void;
}

interface CommandPaletteProps {
	open: boolean;
	onClose: () => void;
	items: CommandItem[];
	/** Called with the item id after its action runs; use for recency tracking. */
	onInvoke?: (id: string) => void;
	/** Optional per-item boost [0, 1] added to fuzzy score before sorting. */
	recencyBoost?: (id: string) => number;
}

export function CommandPalette({
	open,
	onClose,
	items,
	onInvoke,
	recencyBoost,
}: CommandPaletteProps) {
	const [query, setQuery] = useState("");
	const [selectedIndex, setSelectedIndex] = useState(0);
	const inputRef = useRef<HTMLInputElement>(null);

	const close = useCallback(() => {
		setQuery("");
		setSelectedIndex(0);
		onClose();
	}, [onClose]);

	const filtered = useMemo(() => {
		const matchText = (item: CommandItem) => [item.label, ...(item.keywords ?? [])].join(" ");
		const boost = recencyBoost ? (item: CommandItem) => recencyBoost(item.id) : undefined;
		return fuzzyRank(items, query, matchText, boost).map((r) => r.item);
	}, [items, query, recencyBoost]);

	useEffect(() => {
		setSelectedIndex(0);
	}, []);

	useEffect(() => {
		if (open) {
			requestAnimationFrame(() => inputRef.current?.focus());
		}
	}, [open]);

	useEffect(() => {
		if (!open) return;

		function handleKey(e: KeyboardEvent) {
			if (e.key === "Escape") {
				e.preventDefault();
				close();
			} else if (e.key === "ArrowDown") {
				e.preventDefault();
				setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
			} else if (e.key === "ArrowUp") {
				e.preventDefault();
				setSelectedIndex((i) => Math.max(i - 1, 0));
			} else if (e.key === "Enter") {
				e.preventDefault();
				const item = filtered[selectedIndex];
				if (item) {
					item.action();
					onInvoke?.(item.id);
				}
			}
		}

		window.addEventListener("keydown", handleKey);
		return () => window.removeEventListener("keydown", handleKey);
	}, [open, close, filtered, selectedIndex, onInvoke]);

	if (!open) return null;

	return (
		<div className="fixed inset-0 z-[100] flex items-start justify-center pt-[20vh]">
			{/* Backdrop */}
			<button
				type="button"
				aria-label="Close command palette"
				className="absolute inset-0 bg-black/60 backdrop-blur-sm"
				onClick={close}
			/>

			{/* Palette */}
			<div
				className="relative w-full max-w-md rounded-xl border border-border bg-card shadow-card overflow-hidden"
				style={{ animation: "fadeSlideIn 150ms ease-out both" }}
			>
				{/* Search input */}
				<div className="flex items-center gap-3 px-4 py-3 border-b border-border/60">
					<Search className="w-4 h-4 text-muted-foreground shrink-0" />
					<input
						ref={inputRef}
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="Search projects, actions..."
						className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
					/>
					<kbd className="text-[10px] text-muted-foreground/50 bg-secondary/50 rounded px-1.5 py-0.5 border border-border/40">
						ESC
					</kbd>
				</div>

				{/* Results */}
				<div className="max-h-72 overflow-y-auto py-1">
					{filtered.length === 0 ? (
						<div className="px-4 py-6 text-center text-muted-foreground text-xs">
							No results found
						</div>
					) : (
						filtered.map((item, i) => (
							<button
								type="button"
								key={item.id}
								onClick={() => {
									item.action();
									onInvoke?.(item.id);
								}}
								onMouseEnter={() => setSelectedIndex(i)}
								className={cn(
									"w-full flex items-center gap-3 px-4 py-2 text-left transition-colors",
									i === selectedIndex
										? "bg-accent/10 text-accent"
										: "text-foreground hover:bg-secondary/30",
								)}
							>
								{item.color ? (
									<div
										className="w-3 h-3 rounded-full shrink-0"
										style={{ backgroundColor: item.color }}
									/>
								) : (
									<span className="text-muted-foreground shrink-0">{item.icon}</span>
								)}
								<span className="text-sm truncate flex-1">{item.label}</span>
								{item.sublabel && (
									<kbd className="text-[10px] text-muted-foreground/40 bg-secondary/30 rounded px-1.5 py-0.5 border border-border/30 shrink-0">
										{item.sublabel}
									</kbd>
								)}
							</button>
						))
					)}
				</div>
			</div>
		</div>
	);
}
