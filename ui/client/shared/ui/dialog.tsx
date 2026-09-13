/**
 * Dialog primitive — thin wrapper over @radix-ui/react-dialog so every modal
 * in the app gets focus trap, Escape-to-close, role="dialog"+aria-labelledby,
 * scroll lock, and proper portal mounting for free.
 *
 * Renders as a rounded cloud on >=sm screens and a full-width bottom-sheet
 * on phones (the P0 a11y principle calls for "mobile = bottom-sheet drawer
 * on phones"). Existing one-off modals (NewProjectDialog, CoachMemoryDialog)
 * are slated to migrate to this primitive as their owners touch them.
 *
 * Focus goes back to what opened the dialog. Radix returns it only to a
 * `DialogPrimitive.Trigger`, and no dialog here has one — each opens from
 * state — so without this every close left focus on <body>. When a save has
 * taken the opener off the page ("Book time off" became "Change"), the
 * caller's `returnFocus` names what stands in for it.
 */

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type * as React from "react";
import { useRef } from "react";
import { cn } from "../lib";

export interface DialogProps {
	open: boolean;
	onClose: () => void;
	title: string;
	description?: string;
	children: React.ReactNode;
	/** Constrain content width on >= sm. Defaults to "max-w-lg". */
	contentClassName?: string;
	/**
	 * Fires when the dialog has closed, before focus goes back to what opened
	 * it. `preventDefault()` on the event and focus something else instead —
	 * for a close that hands over to a control on the page.
	 */
	onCloseAutoFocus?: (event: Event) => void;
	/**
	 * Where focus goes on close when the control that opened the dialog is no
	 * longer on the page. Unset, or returning nothing, focus stays where the
	 * browser leaves it.
	 */
	returnFocus?: () => HTMLElement | null | undefined;
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
	onCloseAutoFocus,
	returnFocus,
}: DialogProps) {
	// Read while rendering the open: by the time Radix's focus scope mounts, a
	// field inside may have autofocused and the opener is no longer known.
	const opener = useRef<HTMLElement | null>(null);
	const wasOpen = useRef(false);
	if (open && !wasOpen.current) {
		const active = document.activeElement;
		opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
	}
	wasOpen.current = open;

	const handleCloseAutoFocus = (event: Event) => {
		onCloseAutoFocus?.(event);
		if (event.defaultPrevented) return;
		// Radix would focus a Trigger this dialog does not have, and nothing else.
		event.preventDefault();
		const back = opener.current?.isConnected ? opener.current : returnFocus?.();
		opener.current = null;
		back?.focus();
	};

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
						"fixed inset-0 z-[70] bg-veil backdrop-blur-xs",
						"data-[state=open]:animate-in data-[state=open]:fade-in-0",
						"data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
					)}
				/>
				<DialogPrimitive.Content
					onCloseAutoFocus={handleCloseAutoFocus}
					className={cn(
						"fixed z-[71] bg-card text-foreground shadow-card",
						// Mobile: bottom-sheet, full-width, rounded top corners only.
						"inset-x-0 bottom-0 rounded-t-[1.75rem] p-5",
						"max-h-[90vh] overflow-y-auto",
						// >= sm: a centered cloud.
						"sm:inset-auto sm:left-1/2 sm:top-1/2 sm:bottom-auto",
						"sm:-translate-x-1/2 sm:-translate-y-1/2",
						"sm:rounded-[1.75rem] sm:max-h-[85vh]",
						"data-[state=open]:animate-in data-[state=closed]:animate-out",
						"data-[state=open]:slide-in-from-bottom-2 sm:data-[state=open]:slide-in-from-bottom-0 sm:data-[state=open]:fade-in-0",
						contentClassName ?? "sm:w-full sm:max-w-lg",
					)}
				>
					<div className="flex items-start gap-2 mb-3">
						<div className="flex-1">
							<DialogPrimitive.Title className="font-heading text-lg font-extrabold text-foreground">
								{title}
							</DialogPrimitive.Title>
							{description && (
								<DialogPrimitive.Description className="text-xs text-muted-foreground mt-0.5">
									{description}
								</DialogPrimitive.Description>
							)}
						</div>
						<DialogPrimitive.Close
							aria-label="Close"
							className="p-2 -m-2 rounded-full text-muted-foreground/60 hover:text-foreground hover:bg-secondary transition focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
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
