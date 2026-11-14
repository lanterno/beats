/**
 * Index Page
 * Dashboard with productivity score, compact week bar, session feed, and project pulse.
 */
import { CloudOff } from "lucide-react";
import { LoadingSpinner, useProjects } from "@/entities/project";
import { describeError, waitingFor } from "@/shared/api";
import { Button } from "@/shared/ui";
import { DailyBrief } from "./DailyBrief";
import { FlowHeadline } from "./FlowHeadline";
import { Inbox } from "./Inbox";
import { ProductivityScore } from "./ProductivityScore";
import { ProjectPulseList } from "./ProjectPulseList";
import { QuickLog } from "./QuickLog";
import { TodayFeed } from "./TodayFeed";
import { WeekPanel } from "./WeekPanel";

export default function Index() {
	const projects = useProjects();

	// Nothing here draws without the projects, so until they come the page says
	// why: still loading, a server it cannot reach (the read keeps trying, so the
	// page fills in by itself once it answers), or a refusal it gave up on.
	const waiting = waitingFor(projects);
	if (waiting === "loading") {
		return <LoadingSpinner message="Loading your projects..." />;
	}
	if (waiting === "unreachable") {
		return (
			<div className="min-h-screen flex items-center justify-center px-6">
				<div className="text-center max-w-sm" role="status">
					<CloudOff className="w-8 h-8 text-muted-foreground mx-auto mb-4" aria-hidden="true" />
					<p className="text-foreground text-base font-bold">Can't reach the server right now.</p>
					<p className="text-muted-foreground text-sm mt-1">
						The app keeps trying, and this page fills in as soon as the server answers.
					</p>
				</div>
			</div>
		);
	}
	if (waiting === "failed") {
		return (
			<div className="min-h-screen flex items-center justify-center px-6">
				<div className="text-center max-w-sm" role="alert">
					<p className="text-foreground text-base font-bold">Your projects could not be loaded.</p>
					<p className="text-muted-foreground text-sm mt-1">
						{describeError(projects.error, "The server refused the request.")}
					</p>
					<Button variant="outline" size="sm" className="mt-4" onClick={() => projects.refetch()}>
						Try again
					</Button>
				</div>
			</div>
		);
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
