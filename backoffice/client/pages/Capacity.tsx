/**
 * What the platform will cost and how it will behave next quarter: storage
 * per collection and the coach's platform-wide cost, and live health from
 * Cloud Monitoring (shared/ui/HealthPanel.tsx) with refused writes per route.
 */

import { useQuery } from "@tanstack/react-query";
import { get } from "@/shared/api/client";
import type { CapacityReport } from "@/shared/api/schema";
import { counted, dollars, formatBytes, whole } from "@/shared/lib/format";
import { day, Empty, Failed, figure, Loading, Page, Panel, Prose, Table } from "@/shared/ui";
import { HealthPanel } from "@/shared/ui/HealthPanel";

const MONITORING = "https://console.cloud.google.com/monitoring/dashboards?project=beats-476914";

export function Capacity() {
	const { data, error, refetch } = useQuery({
		queryKey: ["capacity"],
		queryFn: () => get<CapacityReport>("/api/operator/capacity"),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const collections = [...data.collections].sort((a, b) => b.storage_bytes - a.storage_bytes);
	const stored = collections.reduce((sum, c) => sum + c.storage_bytes, 0);
	const largest = collections[0];
	const spent = data.coach_cost.reduce((sum, c) => sum + c.cost_usd, 0);

	return (
		<Page
			title="Capacity"
			lead={
				largest
					? `The database takes up ${formatBytes(stored)} across ${counted(collections.length, "collection", "collections")}. The largest is ${largest.name}, at ${formatBytes(largest.storage_bytes)}.`
					: "The database has no collections yet."
			}
		>
			<HealthPanel routes />
			<Panel raised title="Collections">
				<Table
					head={["Collection", figure("Documents"), figure("Storage")]}
					rows={collections.map((c) => [c.name, whole(c.documents), formatBytes(c.storage_bytes)])}
					empty={<Empty title="No collections yet." />}
				/>
			</Panel>
			<Panel
				title="Coach cost"
				note={
					data.coach_cost.length > 0
						? `${dollars(spent)} across the days below, by day and model.`
						: undefined
				}
			>
				<Table
					head={[
						day("Day"),
						"Model",
						figure("Cost"),
						figure("Input tokens"),
						figure("Cache-read tokens"),
						figure("Calls"),
					]}
					rows={data.coach_cost.map((c) => [
						c.day,
						c.model,
						`$${c.cost_usd.toFixed(4)}`,
						whole(c.input_tokens),
						whole(c.cache_read_tokens),
						whole(c.calls),
					])}
					empty={<Empty title="The coach hasn't cost anything yet." />}
				/>
			</Panel>
			<Panel title="Latency, error rates and instances">
				<Prose>
					These aren't rebuilt here.{" "}
					<a href={MONITORING} className="link">
						Open Cloud Monitoring
					</a>
					.
				</Prose>
			</Panel>
		</Page>
	);
}
