import { createRoot } from "react-dom/client";
import { App } from "./app";
import { watchForNewRelease } from "./app/release";
import { wireSession } from "./app/session";

// Before the first render: the session port that shared/ and entities/ read
// through starts out signed-out, and nothing should observe that default.
wireSession();

createRoot(document.getElementById("root")!).render(<App />);

// A build only: the dev server makes no worker. Registered here rather than by
// vite-plugin-pwa's own script, which registers and does nothing else.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
	window.addEventListener("load", () => {
		watchForNewRelease(navigator.serviceWorker).catch(() => {});
	});
}
