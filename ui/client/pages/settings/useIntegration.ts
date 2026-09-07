/**
 * One status/disconnect pair for the biometric integrations.
 *
 * Calendar and GitHub already had query hooks; Fitbit and Oura each carried
 * their own `useState` + `useEffect` + bare `catch {}` copy of the same cycle.
 * This puts all four on the same footing — a cached status, a disconnect that
 * invalidates it, and errors that reach the user instead of being swallowed.
 *
 * How a connection is *made* differs (Fitbit redirects through OAuth, Oura
 * takes a pasted token), so that stays with each section.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { del, describeError, get } from "@/shared/api";

export interface IntegrationStatus {
	connected: boolean;
	[field: string]: unknown;
}

export const integrationKeys = {
	all: ["integration"] as const,
	status: (name: string) => ["integration", name, "status"] as const,
};

export function useIntegration(name: string, label: string) {
	const queryClient = useQueryClient();
	const invalidate = () =>
		queryClient.invalidateQueries({ queryKey: integrationKeys.status(name) });

	const status = useQuery({
		queryKey: integrationKeys.status(name),
		queryFn: () => get<IntegrationStatus>(`/api/${name}/status`),
		staleTime: 30_000,
	});

	const disconnect = useMutation({
		mutationFn: () => del(`/api/${name}/disconnect`),
		onSuccess: () => {
			toast.success(`${label} disconnected`);
			return invalidate();
		},
		onError: (err) => toast.error(describeError(err, `Failed to disconnect ${label}`)),
	});

	return {
		connected: status.data?.connected ?? false,
		details: status.data,
		isLoading: status.isLoading,
		disconnect: disconnect.mutate,
		isDisconnecting: disconnect.isPending,
		refresh: invalidate,
	};
}
