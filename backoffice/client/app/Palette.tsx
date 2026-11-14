/**
 * ⌘K: go to a page, open a command's review, or find one account by its
 * whole address or id. The rules are shared/lib/palette.ts; this is the
 * dialog. Nothing here acts: a command opens its review, and the review is
 * where it is carried out.
 *
 * An address is sent in a POST body, shown in the dialog, and forgotten when
 * it closes — never put in a URL, the browser's history or the recent list.
 * Opening a match navigates by the account's id.
 */

import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { post } from "@/shared/api/client";
import type { AccountMatch } from "@/shared/api/schema";
import { intentOf, pagesFor, reviewsFor } from "@/shared/lib/palette";
import { buttonClass, Failed, Id } from "@/shared/ui";

export function Palette() {
	const dialog = useRef<HTMLDialogElement>(null);
	const [typed, setTyped] = useState("");
	const navigate = useNavigate();
	const lookup = useMutation({
		mutationFn: (address: string) =>
			post<AccountMatch[]>("/api/operator/accounts/lookup", { email: address }),
	});

	useEffect(() => {
		const onKey = (e: KeyboardEvent) => {
			if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
				e.preventDefault();
				dialog.current?.showModal();
			}
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, []);

	const close = () => {
		dialog.current?.close();
	};
	// Whatever was typed, an address included, goes when the dialog does.
	const forget = () => {
		setTyped("");
		lookup.reset();
	};
	const go = (to: string) => {
		close();
		navigate(to);
	};

	const intent = intentOf(typed);
	const destinations = [...pagesFor(intent), ...reviewsFor(intent)];

	const submit = (e: React.FormEvent) => {
		e.preventDefault();
		if (intent.kind === "address") {
			lookup.mutate(intent.address);
			return;
		}
		const first = destinations[0];
		if (first) go(first.to);
	};

	return (
		<>
			<button
				type="button"
				onClick={() => dialog.current?.showModal()}
				className="inline-flex h-8 items-center gap-2 rounded-full bg-wash px-3 text-[13px] hover:bg-wash-strong"
			>
				Go to, or find an account
				<kbd className="font-heading text-ink-muted">⌘K</kbd>
			</button>
			<dialog
				ref={dialog}
				onClose={forget}
				aria-label="Go to"
				className="m-auto w-[min(560px,calc(100vw-2rem))] rounded-[var(--radius-panel)] bg-panel-solid p-0 text-ink shadow-[var(--shadow-raised)] backdrop:bg-ink/30"
			>
				<form onSubmit={submit} className="border-b border-hairline px-5 py-4">
					<input
						// biome-ignore lint/a11y/noAutofocus: a palette exists to be typed into
						autoFocus
						value={typed}
						onChange={(e) => {
							setTyped(e.target.value);
							lookup.reset();
						}}
						placeholder="A page, an account id, or a whole address"
						aria-label="Go to"
						autoComplete="off"
						spellCheck={false}
						className="h-10 w-full bg-transparent text-[15px] outline-none"
					/>
				</form>
				<div className="max-h-[60vh] overflow-y-auto px-2 py-2">
					{intent.kind === "address" ? (
						<AddressResult
							pending={lookup.isPending}
							error={lookup.error}
							matches={lookup.data}
							onOpen={(id) => go(`/accounts/${id}`)}
						/>
					) : null}
					<ul>
						{destinations.map((d) => (
							<li key={d.to}>
								<button
									type="button"
									onClick={() => go(d.to)}
									className="w-full rounded-[var(--radius-tile)] px-3 py-2 text-left text-[14px] hover:bg-wash"
								>
									{d.label}
								</button>
							</li>
						))}
					</ul>
					{intent.kind === "fragment" && destinations.length === 0 ? (
						<p className="px-3 py-2 text-[14px] text-ink-muted">
							No page by that name. To find an account, type its whole address or its id: there is
							no search over people.
						</p>
					) : null}
				</div>
			</dialog>
		</>
	);
}

function AddressResult({
	pending,
	error,
	matches,
	onOpen,
}: {
	pending: boolean;
	error: unknown;
	matches: AccountMatch[] | undefined;
	onOpen: (id: string) => void;
}) {
	if (error) return <Failed bare error={error} />;
	if (pending) return <p className="px-3 py-2 text-[14px]">Looking…</p>;
	if (!matches) {
		return (
			<p className="px-3 py-2 text-[14px] text-ink-muted">
				Press Enter to find the account with exactly this address.
			</p>
		);
	}
	if (matches.length === 0) {
		return (
			<p className="px-3 py-2 text-[14px] text-ink-muted">
				No account has that address. It has to match exactly.
			</p>
		);
	}
	return (
		<ul>
			{matches.map((m) => (
				<li key={m.id} className="flex items-center gap-3 px-3 py-2 text-[14px]">
					<span className="min-w-0 flex-1 break-all">
						{m.email} <Id>{m.id}</Id>
					</span>
					<button type="button" onClick={() => onOpen(m.id)} className={buttonClass("secondary")}>
						Open
					</button>
				</li>
			))}
		</ul>
	);
}
