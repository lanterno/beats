/**
 * Command Palette Component
 * Cmd+K overlay for quick project search and navigation.
 */

import { ArrowRight, BarChart3, Clock, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/shared/lib";

interface CommandItem {
	id: string;
	label: string;
	sublabel?: string;
	icon?: React.ReactNode;
	color?: string;
	action: () => void;
}

interface CommandPaletteProps {
	open: boolean;
	onClose: () => void;
	projects: Array<{ id: string; name: string; color: string }>;
	isTimerRunning: boolean;
	onToggleTimer: () => void;
}

export function CommandPalette({
	open,
	onClose,
	projects,
	isTimerRunning,
	onToggleTimer,
}: CommandPaletteProps) {
	const navigate = useNavigate();
	const [query, setQuery] = useState("");
	const [selectedIndex, setSelectedIndex] = useState(0);
	const inputRef = useRef<HTMLInputElement>(null);

	const close = useCallback(() => {
		setQuery("");
		setSelectedIndex(0);
		onClose();
	}, [onClose]);

	// Build command items
	const items: CommandItem[] = [];

	// Timer action
	items.push({
		id: "timer",
		label: isTimerRunning ? "Stop timer" : "Start timer",
		sublabel: "Space",
		icon: <Clock className="w-4 h-4" />,
		action: () => {
			onToggleTimer();
			close();
		},
	});

	// Navigate to insights
	items.push({
		id: "insights",
		label: "Go to Insights",
		sublabel: "/insights",
		icon: <BarChart3 className="w-4 h-4" />,
		action: () => {
			navigate("/insights");
			close();
		},
	});

	// Navigate to dashboard
	items.push({
		id: "dashboard",
		label: "Go to Dashboard",
		sublabel: "/app",
		icon: <ArrowRight className="w-4 h-4" />,
		action: () => {
			navigate("/app");
			close();
		},
	});

	// Projects
	projects.forEach((p, i) => {
		items.push({
			id: `project-${p.id}`,
			label: p.name,
			sublabel: i < 9 ? `${i + 1}` : undefined,
			color: p.color,
			action: () => {
				navigate(`/project/${p.id}`);
				close();
			},
		});
	});

	// Filter by query
	const filtered = query
		? items.filter((item) => item.label.toLowerCase().includes(query.toLowerCase()))
		: items;

	// Clamp selected index
	useEffect(() => {
		setSelectedIndex(0);
	}, []);

	// Focus input when opened
	useEffect(() => {
		if (open) {
			requestAnimationFrame(() => inputRef.current?.focus());
		}
	}, [open]);

	// Keyboard navigation inside palette
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
				filtered[selectedIndex]?.action();
			}
		}

		window.addEventListener("keydown", handleKey);
		return () => window.removeEventListener("keydown", handleKey);
	}, [open, close, filtered, selectedIndex]);

	if (!open) return null;

	return (
		<div className="fixed inset-0 z-[100] flex items-start justify-center pt-[20vh]">
			{/* Backdrop */}
			<div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={close} />

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
								key={item.id}
								onClick={item.action}
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
