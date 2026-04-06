/**
 * Insights Page
 * Analytics dashboard with contribution heatmap and daily rhythm chart.
 */
import { ContributionHeatmap } from "./ContributionHeatmap";
import { DailyRhythmChart } from "./DailyRhythmChart";

export default function Insights() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-6 space-y-5">
      <h1 className="font-heading text-xl text-foreground">Insights</h1>
      <ContributionHeatmap />
      <DailyRhythmChart />
    </div>
  );
}
