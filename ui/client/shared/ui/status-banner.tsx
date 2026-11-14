/**
 * The status banner (docs/status-page.md): shown in the shell only when the
 * public status file says something is not operational. It polls the file
 * about once a minute and, when the fetch fails, shows nothing — it must
 * never hold up or break the app. Nothing here touches the API.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router";
import { config } from "@/shared/config";
import { fetchStatus, type StatusDoc, showsBanner, statusSentence } from "@/shared/lib/status";

export function StatusBanner() {
	const [doc, setDoc] = useState<StatusDoc | null>(null);
	useEffect(() => {
		if (!config.statusUrl) return;
		let live = true;
		const load = () =>
			fetchStatus(config.statusUrl).then((next) => {
				if (live) setDoc(next);
			});
		load();
		const timer = setInterval(load, 60_000);
		return () => {
			live = false;
			clearInterval(timer);
		};
	}, []);
	if (!config.statusUrl || !showsBanner(doc) || doc === null) return null;
	return (
		<div
			role="status"
			className="lg:ml-72 mx-4 mt-3 rounded-2xl bg-amber-100 px-4 py-2 font-body text-sm text-amber-950 shadow-soft"
		>
			{statusSentence(doc)}
			{doc.message ? ` ${doc.message}` : ""}{" "}
			<Link to="/status" className="underline">
				Status page
			</Link>
		</div>
	);
}
