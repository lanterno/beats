/**
 * Application Root Component
 * Sets up providers and routing with auth protection.
 */
import "../global.css";

import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { initializeAuth, useAuth } from "@/features/auth";
import Clients from "@/pages/clients";
import Coach from "@/pages/coach/Coach";
import HomePage from "@/pages/homepage/HomePage";
import Index from "@/pages/index";
import Insights from "@/pages/insights";
import Digests from "@/pages/insights/Digests";
import MonthlyRetrospective from "@/pages/insights/MonthlyRetrospective";
import YearInReview from "@/pages/insights/YearInReview";
import NotFound from "@/pages/not-found";
import Organisations from "@/pages/organisations";
import ArchivePage from "@/pages/organisations/ArchivePage";
import JoinPage from "@/pages/organisations/JoinPage";
import Organisation from "@/pages/organisations/Organisation";
import Record from "@/pages/organisations/Record";
import Visible from "@/pages/organisations/Visible";
import PlanPage from "@/pages/plan";
import ProjectDetails from "@/pages/project-details";
import ProjectsIndex from "@/pages/projects-index";
import Report from "@/pages/report";
import Settings from "@/pages/settings";
import SsoCallback from "@/pages/sso-callback";
import { Toaster, TooltipProvider } from "@/shared/ui";
import { ErrorBoundary } from "./ErrorBoundary";
import { Layout } from "./Layout";
import { QueryProvider } from "./providers";

/**
 * Protected Route wrapper that redirects to login if not authenticated.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
	const { isAuthenticated, isLoading } = useAuth();

	if (isLoading) {
		return (
			<div className="min-h-screen bg-background flex items-center justify-center">
				<div className="text-muted-foreground">Loading...</div>
			</div>
		);
	}

	if (!isAuthenticated) {
		return <Navigate to="/" replace />;
	}

	return <>{children}</>;
}

/**
 * Public-or-dashboard route: shows homepage if logged out, dashboard if logged in.
 */
function HomeOrDashboard() {
	const { isAuthenticated, isLoading } = useAuth();

	if (isLoading) {
		return (
			<div className="min-h-screen bg-background flex items-center justify-center">
				<div className="text-muted-foreground">Loading...</div>
			</div>
		);
	}

	if (!isAuthenticated) {
		return <HomePage />;
	}

	return <Navigate to="/app" replace />;
}

function AuthInitializer({ children }: { children: React.ReactNode }) {
	useEffect(() => {
		initializeAuth();
	}, []);

	return <>{children}</>;
}

export function App() {
	return (
		<ErrorBoundary>
			<QueryProvider>
				<TooltipProvider>
					<Toaster />
					<AuthInitializer>
						<BrowserRouter>
							<Routes>
								{/* Public routes */}
								<Route path="/" element={<HomeOrDashboard />} />
								{/* Where sign-in providers send the browser back: public,
								    since a sign-in arrives before there is a session. */}
								<Route path="/auth/callback" element={<SsoCallback />} />
								{/* A report link (docs/billing.md, phase 1c): a client opens it
								    with no account, so it sits outside ProtectedRoute and
								    outside Layout — there is nothing here to navigate to. */}
								<Route path="/r/:token" element={<Report />} />
								{/* Protected routes with persistent layout */}
								<Route
									element={
										<ProtectedRoute>
											<Layout />
										</ProtectedRoute>
									}
								>
									<Route path="/app" element={<Index />} />
									<Route path="/insights" element={<Insights />} />
									<Route path="/insights/digests" element={<Digests />} />
									<Route path="/insights/month/:yearMonth" element={<MonthlyRetrospective />} />
									<Route path="/insights/year/:year" element={<YearInReview />} />
									<Route path="/projects" element={<ProjectsIndex />} />
									<Route path="/project/:projectId" element={<ProjectDetails />} />
									<Route path="/clients" element={<Clients />} />
									<Route path="/organisations" element={<Organisations />} />
									<Route path="/organisations/join/:token" element={<JoinPage />} />
									<Route path="/organisations/:id" element={<Organisation />} />
									<Route path="/organisations/:id/record" element={<Record />} />
									<Route path="/organisations/:id/visible" element={<Visible />} />
									<Route path="/organisations/:id/archive" element={<ArchivePage />} />
									<Route path="/plan" element={<PlanPage />} />
									<Route path="/coach" element={<Coach />} />
									<Route path="/settings" element={<Settings />} />
								</Route>

								{/* Fallback */}
								<Route path="*" element={<NotFound />} />
							</Routes>
						</BrowserRouter>
					</AuthInitializer>
				</TooltipProvider>
			</QueryProvider>
		</ErrorBoundary>
	);
}
