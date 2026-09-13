/**
 * Panel — a cloud-white surface floating on the sky: rounded, shadowed, no
 * border. The one card the app has; pages compose it instead of repeating
 * the class string.
 */
import type * as React from "react";

import { cn } from "../lib";

export interface PanelProps extends React.ComponentPropsWithRef<"div"> {
	/** The inner padding as a Tailwind utility. Defaults to `p-6`; pass `p-0` for a flush list. */
	padding?: string;
}

// React 19 passes `ref` as an ordinary prop — no forwardRef needed.
export function Panel({ className, padding = "p-6", ref, ...props }: PanelProps) {
	return (
		<div
			ref={ref}
			className={cn("rounded-[1.625rem] bg-card shadow-soft", padding, className)}
			{...props}
		/>
	);
}
