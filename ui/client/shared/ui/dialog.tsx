/**
 * Dialog primitive — thin wrapper over @radix-ui/react-dialog so every modal
 * in the app gets focus trap, Escape-to-close, role="dialog"+aria-labelledby,
 * scroll lock, and proper portal mounting for free.
 *
 * Renders as a centered card on >=sm screens and a full-width bottom-sheet
 * on phones (the P0 a11y principle calls for "mobile = bottom-sheet drawer
 * on phones"). Existing one-off modals (NewProjectDialog, CoachMemoryDialog)
 * are slated to migrate to this primitive as their owners touch them.
 */

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type * as React from "react";
import { cn } from "../lib";

export interface DialogProps {
	open: boolean;
	onClose: () => void;
	title: string;
	description?: string;
	children: React.ReactNode;
	/** Constrain content width on >= sm. Defaults to "max-w-lg". */
	contentClassName?: string;
}

/**
 * Opinionated app-wide Dialog. Use this for any new modal — manually-rolled
 * modals miss focus trap, scroll lock, and ARIA semantics.
 */
export function Dialog({
	open,
	onClose,
	title,
	description,
	children,
	contentClassName,
}: DialogProps) {
	return (
		<DialogPrimitive.Root
			open={open}
			onOpenChange={(next: boolean) => {
				if (!next) onClose();
			}}
		>
			<DialogPrimitive.Portal>
				<DialogPrimitive.Overlay
					className={cn(
						"fixed inset-0 z-[70] bg-black/50 backdrop-blur-xs",
						"data-[state=open]:animate-in data-[state=open]:fade-in-0",
						"data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
					)}
				/>
				<DialogPrimitive.Content
					className={cn(
						"fixed z-[71] bg-card text-foreground shadow-card",
						// Mobile: bottom-sheet, full-width, rounded top corners only.
						"inset-x-0 bottom-0 rounded-t-2xl border-t border-border/80 p-5",
						"max-h-[90vh] overflow-y-auto",
						// >= sm: centered card.
						"sm:inset-auto sm:left-1/2 sm:top-1/2 sm:bottom-auto",
						"sm:-translate-x-1/2 sm:-translate-y-1/2",
						"sm:rounded-xl sm:border sm:max-h-[85vh]",
						"data-[state=open]:animate-in data-[state=closed]:animate-out",
						"data-[state=open]:slide-in-from-bottom-2 sm:data-[state=open]:slide-in-from-bottom-0 sm:data-[state=open]:fade-in-0",
						contentClassName ?? "sm:w-full sm:max-w-lg",
					)}
				>
					<div className="flex items-start gap-2 mb-3">
						<div className="flex-1">
							<DialogPrimitive.Title className="text-sm font-semibold text-foreground">
								{title}
							</DialogPrimitive.Title>
							{description && (
								<DialogPrimitive.Description className="text-xs text-muted-foreground/70 mt-0.5">
									{description}
								</DialogPrimitive.Description>
							)}
						</div>
						<DialogPrimitive.Close
							aria-label="Close"
							className="p-2 -m-2 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50 transition focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
						>
							<X className="w-4 h-4" />
						</DialogPrimitive.Close>
					</div>
					{children}
				</DialogPrimitive.Content>
			</DialogPrimitive.Portal>
		</DialogPrimitive.Root>
	);
}
