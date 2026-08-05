/**
 * Index Page
 * Dashboard with productivity score, compact week bar, session feed, and project pulse.
 */
import { LoadingSpinner, useProjects } from "@/entities/project";
import { DailyBrief } from "./DailyBrief";
import { FlowHeadline } from "./FlowHeadline";
import { Inbox } from "./Inbox";
import { ProductivityScore } from "./ProductivityScore";
import { ProjectPulseList } from "./ProjectPulseList";
import { QuickLog } from "./QuickLog";
import { TodayFeed } from "./TodayFeed";
import { WeekPanel } from "./WeekPanel";

export default function Index() {
	const { isLoading } = useProjects();

	if (isLoading) {
		return <LoadingSpinner message="Loading your projects..." />;
	}

	return (
		<div className="max-w-6xl mx-auto px-6 py-6">
			<div>
				<ProductivityScore />
			</div>

			<div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-5">
				<DailyBrief />
				<Inbox />
			</div>

			<div className="mt-5">
				<FlowHeadline />
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
