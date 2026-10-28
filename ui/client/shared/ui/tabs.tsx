/**
 * Tabs — the pill tablist of the UX-refresh mockup (docs/mockups/ux-refresh.html).
 *
 * WAI-ARIA tabs pattern: roving tabindex, Left/Right (and Home/End) move and
 * select, `aria-controls`/`aria-labelledby` tie each tab to its panel. The
 * selected pill sits on the card surface inside the wash, as every pill
 * control does. Controlled only: the page owns the value, so a tab can live
 * in the URL when the page wants deep links.
 */

import { createRef, type ReactNode, useMemo } from "react";
import { cn } from "@/shared/lib";

export interface TabItem<T extends string> {
	value: T;
	label: ReactNode;
	/** A small count worn by the tab, e.g. decisions waiting. Omitted when 0. */
	count?: number;
}

interface TabsProps<T extends string> {
	tabs: readonly TabItem<T>[];
	value: T;
	onChange: (value: T) => void;
	/** Names the tablist for assistive tech, e.g. "Organisation sections". */
	label: string;
	className?: string;
}

export function Tabs<T extends string>({ tabs, value, onChange, label, className }: TabsProps<T>) {
	const refs = useMemo(() => tabs.map(() => createRef<HTMLButtonElement>()), [tabs]);

	const select = (index: number) => {
		const tab = tabs[index];
		onChange(tab.value);
		refs[index].current?.focus();
	};

	const onKeyDown = (event: React.KeyboardEvent, index: number) => {
		const last = tabs.length - 1;
		const next =
			event.key === "ArrowRight"
				? (index + 1) % tabs.length
				: event.key === "ArrowLeft"
					? (index + last) % tabs.length
					: event.key === "Home"
						? 0
						: event.key === "End"
							? last
							: null;
		if (next === null) return;
		event.preventDefault();
		select(next);
	};

	return (
		<div
			role="tablist"
			aria-label={label}
			className={cn(
				"flex gap-1.5 rounded-full bg-secondary p-1 w-max max-w-full overflow-x-auto",
				className,
			)}
		>
			{tabs.map((tab, index) => {
				const selected = tab.value === value;
				return (
					<button
						key={tab.value}
						ref={refs[index]}
						type="button"
						role="tab"
						id={`tab-${tab.value}`}
						aria-selected={selected}
						aria-controls={`tabpanel-${tab.value}`}
						tabIndex={selected ? 0 : -1}
						onClick={() => select(index)}
						onKeyDown={(event) => onKeyDown(event, index)}
						className={cn(
							"whitespace-nowrap rounded-full px-4 py-1.5 font-heading text-[13px] font-bold transition-colors",
							"focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
							selected
								? "bg-card text-foreground shadow-soft"
								: "text-muted-foreground hover:text-foreground",
						)}
					>
						{tab.label}
						{tab.count ? (
							<span className="ml-1.5 rounded-full bg-destructive px-1.5 text-[11px] font-bold text-destructive-foreground">
								{tab.count}
								<span className="sr-only"> waiting</span>
							</span>
						) : null}
					</button>
				);
			})}
		</div>
	);
}

/** The panel a tab controls; renders only while selected. */
export function TabPanel<T extends string>({
	value,
	current,
	children,
	className,
}: {
	value: T;
	current: T;
	children: ReactNode;
	className?: string;
}) {
	if (value !== current) return null;
	return (
		<div
			role="tabpanel"
			id={`tabpanel-${value}`}
			aria-labelledby={`tab-${value}`}
			className={className}
		>
			{children}
		</div>
	);
}
