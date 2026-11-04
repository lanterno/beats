/**
 * The control plane's shell: a flat nav over dense pages. Deliberately not
 * the sky — an operator should never be unsure which surface they are on.
 */

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BrowserRouter, NavLink, Route, Routes } from "react-router";
import { Abuse } from "@/pages/Abuse";
import { Account, Accounts } from "@/pages/Accounts";
import { Attention } from "@/pages/Attention";
import { Capacity } from "@/pages/Capacity";
import { Compliance } from "@/pages/Compliance";
import { Organisation, Organisations } from "@/pages/Organisations";
import { get } from "@/shared/api/client";
import type { OperatorMe } from "@/shared/api/schema";
import { APP_NAME } from "@/shared/config/brand";

const queryClient = new QueryClient({
	defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const PLACES = [
	["/", "Attention"],
	["/accounts", "Accounts"],
	["/organisations", "Organisations"],
	["/abuse", "Abuse"],
	["/capacity", "Capacity"],
	["/compliance", "Compliance"],
] as const;

function Shell() {
	const me = useQuery({ queryKey: ["me"], queryFn: () => get<OperatorMe>("/api/operator/me") });
	return (
		<div className="min-h-screen">
			<header className="border-b border-neutral-200 bg-white px-4 py-2 flex items-baseline gap-6">
				<span className="font-semibold">{APP_NAME} — control plane</span>
				<nav className="flex gap-4 text-sm">
					{PLACES.map(([to, label]) => (
						<NavLink
							key={to}
							to={to}
							end={to === "/"}
							className={({ isActive }) =>
								isActive ? "font-semibold underline" : "text-neutral-600 hover:underline"
							}
						>
							{label}
						</NavLink>
					))}
				</nav>
				<span className="ml-auto text-xs text-neutral-500">
					{me.data ? `${me.data.email} (${me.data.role})` : ""}
				</span>
			</header>
			<main className="mx-auto max-w-5xl px-4 py-6">
				<Routes>
					<Route path="/" element={<Attention />} />
					<Route path="/accounts" element={<Accounts />} />
					<Route path="/accounts/:id" element={<Account />} />
					<Route path="/organisations" element={<Organisations />} />
					<Route path="/organisations/:id" element={<Organisation />} />
					<Route path="/abuse" element={<Abuse />} />
					<Route path="/capacity" element={<Capacity />} />
					<Route path="/compliance" element={<Compliance />} />
				</Routes>
			</main>
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
