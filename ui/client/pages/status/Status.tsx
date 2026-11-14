/**
 * The status page (docs/status-page.md): what is happening, in a plain
 * sentence first, then the last posts. Public, outside ProtectedRoute and
 * Layout, and it imports nothing that needs a session or the API: it reads
 * one public file, so it still works when the API is down — the only time
 * it matters. Its failure state says the status could not be loaded, never
 * "all good".
 */

import { useEffect, useState } from "react";
import { config } from "@/shared/config";
import { APP_NAME } from "@/shared/config/brand";
import { fetchStatus, type StatusDoc, statusSentence } from "@/shared/lib/status";
import { Panel, SkyBackdrop } from "@/shared/ui";

type Loaded = { kind: "loading" } | { kind: "failed" } | { kind: "ok"; doc: StatusDoc };

const when = (iso: string): string => {
	const d = new Date(iso);
	return Number.isNaN(d.getTime())
		? iso
		: d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

const TONE: Record<StatusDoc["state"], string> = {
	operational: "bg-emerald-500",
	degraded: "bg-amber-500",
	outage: "bg-red-500",
	maintenance: "bg-sky-500",
};

export function Status() {
	const [loaded, setLoaded] = useState<Loaded>({ kind: "loading" });
	useEffect(() => {
		let live = true;
		const load = () =>
			fetchStatus(config.statusUrl).then((doc) => {
				if (live) setLoaded(doc ? { kind: "ok", doc } : { kind: "failed" });
			});
		load();
		const timer = setInterval(load, 60_000);
		return () => {
			live = false;
			clearInterval(timer);
		};
	}, []);

	return (
		<>
			<SkyBackdrop />
			<main className="on-sky min-h-screen px-4 py-10 sm:py-16">
				<div className="mx-auto w-full max-w-2xl space-y-6">
					<h1 className="font-heading text-3xl font-extrabold">{APP_NAME} status</h1>
					<Panel>
						{loaded.kind === "loading" ? (
							<p className="font-body text-lg">Loading the status…</p>
						) : loaded.kind === "failed" ? (
							<p className="font-body text-lg">
								The status could not be loaded. That says nothing about whether {APP_NAME} is
								working; try again in a moment.
							</p>
						) : (
							<div className="space-y-2">
								<p className="flex items-center gap-3 font-body text-lg font-bold">
									<span
										aria-hidden="true"
										className={`inline-block size-3 rounded-full ${TONE[loaded.doc.state]}`}
									/>
									{statusSentence(loaded.doc)}
								</p>
								{loaded.doc.message ? (
									<p className="font-body text-base">{loaded.doc.message}</p>
								) : null}
								<p className="font-body text-sm text-muted-foreground">
									Updated {when(loaded.doc.updated_at)}. This page is checked about once a minute
									and works even when the app does not.
								</p>
							</div>
						)}
					</Panel>
					{loaded.kind === "ok" && loaded.doc.posts.length > 0 ? (
						<Panel padding="p-0">
							<h2 className="px-6 pt-5 pb-2 font-heading text-xl font-bold">Recent updates</h2>
							<ol className="divide-y divide-border">
								{loaded.doc.posts.map((post) => (
									<li key={post.at} className="px-6 py-3">
										<p className="font-body text-sm text-muted-foreground">
											{when(post.at)} · {post.state}
											{post.affected.length ? ` · ${post.affected.join(", ")}` : ""}
										</p>
										<p className="font-body text-base">{post.message}</p>
									</li>
								))}
							</ol>
						</Panel>
					) : null}
				</div>
			</main>
		</>
	);
}
