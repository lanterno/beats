/**
 * TanStack Query Provider
 * Configures the query client for data fetching throughout the app.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

/**
 * Configure the query client with sensible defaults
 */
const queryClient = new QueryClient({
	defaultOptions: {
		queries: {
			// Data is considered fresh for 30 seconds
			staleTime: 30 * 1000,
			// Keep unused data in cache for 5 minutes
			gcTime: 5 * 60 * 1000,
			// Retry failed requests up to 2 times
			retry: 2,
			// Don't refetch every query on window focus — staleTime handles freshness
			refetchOnWindowFocus: false,
		},
		mutations: {
			// Retry failed mutations once
			retry: 1,
		},
	},
});

interface QueryProviderProps {
	children: ReactNode;
}

/**
 * Provides TanStack Query context to the application
 */
export function QueryProvider({ children }: QueryProviderProps) {
	return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/**
 * Export the query client for use in components that need direct access
 * (e.g., for cache invalidation after mutations)
 */
export { queryClient };
