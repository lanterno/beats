/**
 * The control plane's shell: a sidebar over the sky, as the app has it, a
 * topbar saying who is signed in, and the routes. "Back office" is on every
 * page at every width, so an operator is never unsure which surface they
 * are on. The places themselves are listed once, in places.ts.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { Account, Accounts } from "@/pages/Accounts";
import { Attention } from "@/pages/Attention";
import { Audit } from "@/pages/Audit";
import { Capacity } from "@/pages/Capacity";
import { Compliance } from "@/pages/Compliance";
import { Jobs } from "@/pages/Jobs";
import { Organisation, Organisations } from "@/pages/Organisations";
import { Trust } from "@/pages/Trust";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

const queryClient = new QueryClient({
	defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function Shell() {
	return (
		<div className="min-h-screen lg:flex">
			<Sidebar />
			<div className="min-w-0 flex-1">
				<Topbar />
				<main className="px-4 py-6 sm:px-8 sm:py-8">
					<div className="mx-auto max-w-[var(--content-max)]">
						<Routes>
							<Route path="/" element={<Attention />} />
							<Route path="/accounts" element={<Accounts />} />
							<Route path="/accounts/:id" element={<Account />} />
							<Route path="/organisations" element={<Organisations />} />
							<Route path="/organisations/:id" element={<Organisation />} />
							<Route path="/trust" element={<Trust />} />
							<Route path="/capacity" element={<Capacity />} />
							<Route path="/jobs" element={<Jobs />} />
							<Route path="/audit" element={<Audit />} />
							<Route path="/compliance" element={<Compliance />} />
							{/* The page's old address, for a bookmark made before it was renamed. */}
							<Route path="/abuse" element={<Navigate to="/trust" replace />} />
						</Routes>
					</div>
				</main>
			</div>
		</div>
	);
}

export function App() {
	return (
		<QueryClientProvider client={queryClient}>
			<BrowserRouter>
				<Shell />
			</BrowserRouter>
		</QueryClientProvider>
	);
}
