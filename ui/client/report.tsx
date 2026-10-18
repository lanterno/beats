/**
 * The report page's entry (report.html). It draws one page and starts
 * nothing of the app's: no session wiring, no query client, no service
 * worker, no analytics (docs/billing.md, *The public page*). The two brand
 * faces are their Latin subsets from Fontsource, served from this origin;
 * other scripts fall back to the system face.
 */
import "./report-zod";
import "@fontsource/zen-maru-gothic/latin-400.css";
import "@fontsource/zen-maru-gothic/latin-500.css";
import "@fontsource/zen-maru-gothic/latin-700.css";
import "@fontsource/m-plus-rounded-1c/latin-500.css";
import "@fontsource/m-plus-rounded-1c/latin-700.css";
import "@fontsource/m-plus-rounded-1c/latin-800.css";
import "./report.css";
import { createRoot } from "react-dom/client";
import { ReportPage } from "./pages/report";

createRoot(document.getElementById("root")!).render(<ReportPage />);
