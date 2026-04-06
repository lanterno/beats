/**
 * Index Page
 * Dashboard with compact week bar, today's session feed, and project pulse list.
 */
import { LoadingSpinner, useProjects } from "@/entities/project";
import { WeekPanel } from "./WeekPanel";
import { TodayFeed } from "./TodayFeed";
import { ProjectPulseList } from "./ProjectPulseList";

export default function Index() {
  const { isLoading } = useProjects();

  if (isLoading) {
    return <LoadingSpinner message="Loading your projects..." />;
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-6">
      <WeekPanel />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mt-5">
        <div className="lg:col-span-3">
          <TodayFeed />
        </div>
        <div className="lg:col-span-2">
          <ProjectPulseList />
        </div>
      </div>
    </div>
  );
}
