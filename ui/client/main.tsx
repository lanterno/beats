import { registerSW } from "virtual:pwa-register";
import { createRoot } from "react-dom/client";
import { App } from "./app";
import { wireSession } from "./app/session";

// Before the first render: the session port that shared/ and entities/ read
// through starts out signed-out, and nothing should observe that default.
wireSession();

// The app's service worker, registered here rather than by a script the PWA
// plugin injects into every HTML entry, so the report page never carries it
// (docs/billing.md, *The public page*). An update takes over on its own
// (`registerType: "autoUpdate"`) and, as before, never reloads the page: a
// reload under an open dialog would lose what it holds, a new report link
// among it.
registerSW({ onNeedReload: () => {} });

createRoot(document.getElementById("root")!).render(<App />);
