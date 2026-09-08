import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CalendarStatus } from "@/shared/api";
import { connectCalendar, disconnectCalendar, fetchCalendarStatus } from "./calendarApi";

export const calendarKeys = {
	all: ["calendar"] as const,
	status: () => [...calendarKeys.all, "status"] as const,
	events: (start: string, end: string) => [...calendarKeys.all, "events", start, end] as const,
};

export function useCalendarStatus() {
	return useQuery<CalendarStatus>({
		queryKey: calendarKeys.status(),
		queryFn: fetchCalendarStatus,
		staleTime: 60_000,
	});
}

export function useConnectCalendar() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: connectCalendar,
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: calendarKeys.all });
		},
	});
}

export function useDisconnectCalendar() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: disconnectCalendar,
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: calendarKeys.all });
		},
	});
}
