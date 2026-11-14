/**
 * Links into the Google Cloud console, for the deployment the operator API
 * runs in.
 *
 * Two of the control plane's signals are kept nowhere (docs/backoffice.md
 * § *Abuse*): a per-account write refusal and a restore's size are each a
 * line in the API's log and a counter in Cloud Monitoring, never a document.
 * So the pages that want them link to the query rather than show a number —
 * the same shape as the health panel's link to the dashboards.
 *
 * The project and the API's service name come from the operator API
 * (`/api/operator/deployment`), which reads the project off the metadata
 * server it runs on. Off Google Cloud there is no project, and so no link.
 */

import { useQuery } from "@tanstack/react-query";
import { get } from "@/shared/api/client";
import type { Deployment } from "@/shared/api/schema";

const CONSOLE = "https://console.cloud.google.com";

/** Logs Explorer, over a query, for the last `days` days. */
export function logsQuery(project: string, query: string, days: number): string {
	// Logs Explorer reads the query out of a `;`-separated path segment, not
	// the search string, so the newlines and quotes in it are percent-encoded
	// rather than left for the query string's own rules.
	const encoded = encodeURIComponent(query.trim());
	return `${CONSOLE}/logs/query;query=${encoded};duration=P${days}D?project=${encodeURIComponent(project)}`;
}

/**
 * One log-based metric's chart in Metrics Explorer. `pageState` is the
 * console's own serialisation and it normalises what it does not recognise,
 * so this opens the explorer on the right metric rather than on an exact
 * chart.
 */
export function metricChart(project: string, metric: string): string {
	return `${CONSOLE}/monitoring/metrics-explorer?project=${encodeURIComponent(project)}&pageState=${encodeURIComponent(
		JSON.stringify({
			xyChart: {
				dataSets: [
					{
						timeSeriesFilter: {
							filter: `metric.type="logging.googleapis.com/user/${metric}"`,
						},
					},
				],
			},
		}),
	)}`;
}

export interface ConsoleLinks {
	/** Monitoring's dashboards, the API's among them (terraform/monitoring.tf). */
	monitoring: string;
	/** Cloud Run's services, which say whether a revision became ready. */
	cloudRun: string;
	/** The billing account the project is charged to. */
	billing: string;
	/** The API's own log lines carrying a marker, over the last `days` days. */
	apiLog: (marker: string, days: number) => string;
	/** One of the API's log-based metrics, by the name after the service's. */
	apiMetric: (name: string) => string;
}

/** The deployment's links, or null where it has no project to link into. */
export function consoleLinks(deployment: Deployment): ConsoleLinks | null {
	const { project, api_service: service } = deployment;
	if (!project) return null;
	const log = `resource.type="cloud_run_revision"\nresource.labels.service_name="${service}"`;
	const scope = `project=${encodeURIComponent(project)}`;
	return {
		monitoring: `${CONSOLE}/monitoring/dashboards?${scope}`,
		cloudRun: `${CONSOLE}/run?${scope}`,
		billing: `${CONSOLE}/billing/linkedaccount?${scope}`,
		apiLog: (marker, days) => logsQuery(project, `${log}\ntextPayload:"${marker}"`, days),
		// The metrics are named under the service (terraform/monitoring.tf).
		apiMetric: (name) => metricChart(project, `${service}/${name}`),
	};
}

/** The console links, once the operator API has said where it runs. */
export function useConsole(): ConsoleLinks | null {
	const deployment = useQuery({
		queryKey: ["deployment"],
		queryFn: () => get<Deployment>("/api/operator/deployment"),
		// It changes only with a deploy; a minute keeps a failed read from sticking.
		staleTime: 60_000,
	});
	return deployment.data ? consoleLinks(deployment.data) : null;
}
