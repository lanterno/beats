/**
 * A question put to the user as a promise: `confirm(...)` opens a small
 * dialog and resolves true on its confirm button, false on Cancel, Escape
 * or the close button. For a step in the middle of a flow — a write the API
 * answered with "this changes a month already over" — where the caller
 * needs the answer before it goes on, rather than a dialog of its own state.
 *
 * Render `confirmDialog` once in the caller's tree; it is nothing while no
 * question is open. Opened over another dialog it stacks above it, and
 * focus goes back to the control that was focused when it opened.
 */

import { type ReactNode, useRef, useState } from "react";
import { Button } from "./button";
import { Dialog } from "./dialog";

export interface ConfirmRequest {
	title: string;
	/** The question in full: what happens if the user agrees. */
	detail: string;
	confirmLabel: string;
	cancelLabel?: string;
	/**
	 * "danger" draws the confirm button in the destructive tone. The accent
	 * marks a page's primary action; removing someone or deleting something
	 * is not that, and the sunlit button made it read as the expected step.
	 */
	tone?: "danger";
}

export function useConfirm(): {
	confirm: (request: ConfirmRequest) => Promise<boolean>;
	confirmDialog: ReactNode;
} {
	const [request, setRequest] = useState<ConfirmRequest | null>(null);
	const resolver = useRef<((answer: boolean) => void) | null>(null);

	const answer = (value: boolean) => {
		resolver.current?.(value);
		resolver.current = null;
		setRequest(null);
	};

	const confirm = (next: ConfirmRequest) =>
		new Promise<boolean>((resolve) => {
			// A question still open is answered no: only one is asked at a time.
			resolver.current?.(false);
			resolver.current = resolve;
			setRequest(next);
		});

	const confirmDialog = request ? (
		<Dialog
			open
			onClose={() => answer(false)}
			title={request.title}
			contentClassName="sm:w-full sm:max-w-[400px]"
		>
			<p className="text-[13px] leading-normal font-medium text-foreground">{request.detail}</p>
			<div className="flex justify-end gap-2.5 mt-[18px]">
				<Button type="button" variant="secondary" size="sm" onClick={() => answer(false)}>
					{request.cancelLabel ?? "Cancel"}
				</Button>
				<Button
					type="button"
					size="sm"
					variant={request.tone === "danger" ? "destructive" : "default"}
					onClick={() => answer(true)}
				>
					{request.confirmLabel}
				</Button>
			</div>
		</Dialog>
	) : null;

	return { confirm, confirmDialog };
}
