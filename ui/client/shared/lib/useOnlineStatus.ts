/**
 * Online Status Hook
 * Tracks browser online/offline state via navigator.onLine and events.
 * Optionally calls a callback when connectivity is restored.
 */
import { useEffect, useRef, useState } from "react";

export function useOnlineStatus(onReconnect?: () => void): boolean {
	const [online, setOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);
	const onReconnectRef = useRef(onReconnect);
	onReconnectRef.current = onReconnect;

	useEffect(() => {
		const goOnline = () => {
			setOnline(true);
			onReconnectRef.current?.();
		};
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
