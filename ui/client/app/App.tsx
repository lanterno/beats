/**
 * Application Root Component
 * Sets up providers and routing with auth protection.
 */
import "../global.css";

import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster, TooltipProvider } from "@/shared/ui";
import { QueryProvider } from "./providers";
import Index from "@/pages/index";
import ProjectDetails from "@/pages/project-details";
import NotFound from "@/pages/not-found";
import { LoginPage, useAuth, initializeAuth } from "@/features/auth";
import { Layout } from "./Layout";

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
              {/* Public route */}
              <Route path="/login" element={<LoginPage />} />

              {/* Protected routes with persistent layout */}
              <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
                <Route path="/" element={<Index />} />
                <Route path="/project/:projectId" element={<ProjectDetails />} />
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
