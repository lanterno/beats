/**
 * Index Page
 * Dashboard with today's plan, compact week bar, session feed, and project pulse.
 */
import { useMemo } from "react";
import { LoadingSpinner, useProjects } from "@/entities/project";
import { useTodaySessions } from "@/entities/session";
import { Inbox } from "./Inbox";
import { ProductivityScore } from "./ProductivityScore";
import { ProjectPulseList } from "./ProjectPulseList";
import { QuickLog } from "./QuickLog";
import { TodayFeed } from "./TodayFeed";
import { TodaysPlan } from "./TodaysPlan";
import { WeekPanel } from "./WeekPanel";

export default function Index() {
	const { isLoading } = useProjects();
	const { data: todaySessions } = useTodaySessions();

	const trackedMinutesByProject = useMemo(() => {
		const map: Record<string, number> = {};
		for (const s of todaySessions ?? []) {
			if (s.projectId && s.duration > 0) {
				map[s.projectId] = (map[s.projectId] ?? 0) + s.duration;
			}
		}
		return map;
	}, [todaySessions]);

	if (isLoading) {
		return <LoadingSpinner message="Loading your projects..." />;
	}

	return (
		<div className="max-w-6xl mx-auto px-6 py-6">
			<div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
				<div className="lg:col-span-2">
					<TodaysPlan trackedMinutesByProject={trackedMinutesByProject} />
				</div>
				<div>
					<ProductivityScore />
				</div>
			</div>

			<div className="mt-5">
				<Inbox />
			</div>

			<div className="mt-5">
				<WeekPanel />
			</div>

			<div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mt-5">
				<div className="lg:col-span-3 space-y-4">
					<TodayFeed />
					<QuickLog />
				</div>
				<div className="lg:col-span-2">
					<ProjectPulseList />
				</div>
			</div>
		</div>
	);
}
