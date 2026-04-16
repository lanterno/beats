/**
 * Application Root Component
 * Sets up providers and routing with auth protection.
 */
import "../global.css";

import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { initializeAuth, LoginPage, useAuth } from "@/features/auth";
import Coach from "@/pages/coach/Coach";
import HomePage from "@/pages/homepage/HomePage";
import Index from "@/pages/index";
import Insights from "@/pages/insights";
import Digests from "@/pages/insights/Digests";
import MonthlyRetrospective from "@/pages/insights/MonthlyRetrospective";
import YearInReview from "@/pages/insights/YearInReview";
import NotFound from "@/pages/not-found";
import PlanPage from "@/pages/plan";
import ProjectDetails from "@/pages/project-details";
import Settings from "@/pages/settings";
import { Toaster, TooltipProvider } from "@/shared/ui";
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
		return <Navigate to="/login" replace />;
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

/**
 * Auth initializer component.
 */
function AuthInitializer({ children }: { children: React.ReactNode }) {
	useEffect(() => {
		initializeAuth();
	}, []);

	return <>{children}</>;
}

export function App() {
	return (
		<QueryProvider>
			<TooltipProvider>
				<Toaster />
				<AuthInitializer>
					<BrowserRouter>
						<Routes>
							{/* Public routes */}
							<Route path="/" element={<HomeOrDashboard />} />
							<Route path="/login" element={<LoginPage />} />

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
								<Route path="/project/:projectId" element={<ProjectDetails />} />
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
	);
}
