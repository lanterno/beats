import { createRoot } from "react-dom/client";
import { App } from "./app";
import { wireSession } from "./app/session";

// Before the first render: the session port that shared/ and entities/ read
// through starts out signed-out, and nothing should observe that default.
wireSession();

createRoot(document.getElementById("root")!).render(<App />);
