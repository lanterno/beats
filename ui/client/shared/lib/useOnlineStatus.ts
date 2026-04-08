/**
 * Online Status Hook
 * Tracks browser online/offline state via navigator.onLine and events.
 */
import { useEffect, useState } from "react";

export function useOnlineStatus(): boolean {
	const [online, setOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);

	useEffect(() => {
		const goOnline = () => setOnline(true);
		const goOffline = () => setOnline(false);
		window.addEventListener("online", goOnline);
		window.addEventListener("offline", goOffline);
		return () => {
			window.removeEventListener("online", goOnline);
			window.removeEventListener("offline", goOffline);
		};
	}, []);

	return online;
}
