/**
 * What the platform will cost and how it will behave next quarter: storage
 * per collection and the coach's platform-wide cost. Latency, error rates
 * and instance counts are Cloud Monitoring's — linked, not rebuilt.
 */

import { useQuery } from "@tanstack/react-query";
import { get } from "@/shared/api/client";
import type { CapacityReport } from "@/shared/api/schema";
import { formatBytes } from "@/shared/lib/format";
import { Failed, Loading, Section, Table } from "@/shared/ui";

const MONITORING = "https://console.cloud.google.com/monitoring/dashboards?project=beats-476914";

export function Capacity() {
	const { data, error } = useQuery({
		queryKey: ["capacity"],
		queryFn: () => get<CapacityReport>("/api/operator/capacity"),
	});
	if (error) return <Failed error={error} />;
	if (!data) return <Loading />;

	return (
		<>
			<Section title="Collections">
				<Table
					head={["Collection", "Documents", "Storage"]}
					rows={data.collections.map((c) => [c.name, c.documents, formatBytes(c.storage_bytes)])}
				/>
			</Section>
			<Section title="Coach cost, by day and model">
				<Table
					head={["Day", "Model", "Cost", "Input tokens", "Cache-read tokens", "Calls"]}
					rows={data.coach_cost.map((c) => [
						c.day,
						c.model,
						`$${c.cost_usd.toFixed(4)}`,
						c.input_tokens,
						c.cache_read_tokens,
						c.calls,
					])}
				/>
			</Section>
			<p className="text-sm text-neutral-500">
				Latency, error rates and instances:{" "}
				<a href={MONITORING} className="underline">
					Cloud Monitoring
				</a>
				.
			</p>
		</>
	);
}
