/**
 * ReportPage — `/report#lpr_…`, what a client opens from a report link: the
 * report, or one dead state for every link that does not answer (turned
 * off, ended, never made, cut short in an email). It reads the fragment, so
 * a reload and a bookmark work; no fragment, or a malformed one, is the dead
 * state with no request. A page restored from the back-forward cache asks
 * again, so Back after the link was turned off shows it dead.
 *
 * `document.title` stays "Hours report" (report.html): the client's name is
 * never put where history sync or a previewer would read it.
 *
 * While the page prints, the fragment comes off the address. A browser
 * prints the address in each page's footer, fragment and all, and the
 * fragment is the link: the PDF a client saves goes on to an accounts
 * folder or an email archive, and would carry a working link with it. The
 * print button takes it off before it asks to print; Ctrl+P (or ⌘P) takes
 * it off on `beforeprint`, which some browsers fire after they have read
 * the address, so report.css also leaves the browser no room for its own
 * header and footer. `afterprint` puts it back, so a reload still works.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { APP_NAME } from "@/shared/config";
import { Button } from "@/shared/ui/button";
import { Panel } from "@/shared/ui/panel";
import { ClientReportView } from "@/widgets/client-report";
import { fetchReport, type ReportState, tokenFromHash } from "./fetchReport";

const MESSAGE = "text-[14px] font-medium text-foreground";

export function ReportPage() {
	const [state, setState] = useState<ReportState>(() =>
		tokenFromHash(window.location.hash) ? { kind: "loading" } : { kind: "dead" },
	);
	// Only the latest request's answer is drawn.
	const latest = useRef(0);
	// The fragment taken off the address while the page prints.
	const printing = useRef<string | null>(null);

	const hideToken = useCallback(() => {
		const { hash, pathname, search } = window.location;
		if (printing.current !== null || !hash) return;
		printing.current = hash;
		window.history.replaceState(window.history.state, "", `${pathname}${search}`);
	}, []);

	const restoreToken = useCallback(() => {
		const hash = printing.current;
		if (hash === null) return;
		printing.current = null;
		const { pathname, search } = window.location;
		window.history.replaceState(window.history.state, "", `${pathname}${search}${hash}`);
	}, []);

	const load = useCallback(async () => {
		const token = tokenFromHash(window.location.hash);
		const request = ++latest.current;
		if (!token) {
			setState({ kind: "dead" });
			return;
		}
		setState({ kind: "loading" });
		const next = await fetchReport(token);
		if (request === latest.current) setState(next);
	}, []);

	useEffect(() => {
		void load();
		const onShow = (event: PageTransitionEvent) => {
			if (event.persisted) void load();
		};
		const onHash = () => void load();
		window.addEventListener("pageshow", onShow);
		window.addEventListener("hashchange", onHash);
		window.addEventListener("beforeprint", hideToken);
		window.addEventListener("afterprint", restoreToken);
		return () => {
			window.removeEventListener("pageshow", onShow);
			window.removeEventListener("hashchange", onHash);
			window.removeEventListener("beforeprint", hideToken);
			window.removeEventListener("afterprint", restoreToken);
		};
	}, [load, hideToken, restoreToken]);

	const print = () => {
		hideToken();
		// A task later, so the browser has the plain address before it
		// reads it for the footer. Printing blocks in most browsers; where
		// it does not, `afterprint` puts the fragment back.
		window.setTimeout(() => {
			window.print();
			restoreToken();
		}, 0);
	};

	return (
		<main className="mx-auto w-full max-w-3xl px-4 py-8 sm:py-12 print:px-0 print:pt-[12mm] print:pb-0 print:max-w-none">
			{state.kind === "ready" ? (
				<ClientReportView
					report={state.report}
					today={new Date()}
					action={
						<Button
							type="button"
							variant="outline"
							size="sm"
							className="print:hidden"
							onClick={print}
						>
							Print or save as PDF
						</Button>
					}
				/>
			) : (
				<Panel padding="px-5 py-6 sm:px-8 sm:py-8">
					<p className="font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
						Hours report
					</p>
					{state.kind === "loading" && (
						<p className={`${MESSAGE} mt-2`} role="status">
							Loading the report…
						</p>
					)}
					{state.kind === "dead" && (
						<p className={`${MESSAGE} mt-2`}>
							This report link isn't valid. It may have been turned off or have ended, or the
							address may be incomplete. Ask whoever sent it for a new one.
						</p>
					)}
					{state.kind === "limited" && (
						<p className={`${MESSAGE} mt-2`}>Too many tries just now. Wait a minute and reload.</p>
					)}
					{state.kind === "unreachable" && (
						<div className="mt-2 flex flex-wrap items-center gap-3">
							<p className={MESSAGE}>{APP_NAME} can't be reached right now.</p>
							<Button type="button" variant="outline" size="sm" onClick={() => void load()}>
								Try again
							</Button>
						</div>
					)}
				</Panel>
			)}
		</main>
	);
}
