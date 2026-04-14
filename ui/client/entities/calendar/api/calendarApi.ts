/**
 * Calendar API Functions
 */

import type { CalendarEvent, CalendarStatus } from "@/shared/api";
import {
	CalendarEventListSchema,
	CalendarStatusSchema,
	del,
	get,
	parseApiResponse,
	post,
} from "@/shared/api";

export async function fetchCalendarAuthUrl(): Promise<string> {
	const data = await get<{ url: string }>("/api/calendar/auth-url");
	return data.url;
}

export async function connectCalendar(code: string): Promise<void> {
	await post<void>(`/api/calendar/connect?code=${encodeURIComponent(code)}`);
}

export async function fetchCalendarEvents(start: string, end: string): Promise<CalendarEvent[]> {
	const data = await get<unknown>(
		`/api/calendar/events?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
	);
	return parseApiResponse(CalendarEventListSchema, data);
}

export async function disconnectCalendar(): Promise<void> {
	await del<void>("/api/calendar/disconnect");
}

export async function fetchCalendarStatus(): Promise<CalendarStatus> {
	const data = await get<unknown>("/api/calendar/status");
	return parseApiResponse(CalendarStatusSchema, data);
}
