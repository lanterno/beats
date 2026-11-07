/**
 * Links into the Google Cloud console.
 *
 * Two of the control plane's signals are kept nowhere (docs/backoffice.md
 * § *Abuse*): a per-account write refusal and a restore's size are each a
 * line in the API's log and a counter in Cloud Monitoring, never a document.
 * So the pages that want them link to the query rather than show a number —
 * the same shape as Capacity's link to the latency dashboard.
 *
 * The project is hard-coded because there is one deployment (the root
 * CLAUDE.md § *Infrastructure*); a second would make this a build-time value
 * like `VITE_API_URL`.
 */

const PROJECT = "beats-476914";

/** Logs Explorer, over a query, for the last `days` days. */
export function logsQuery(query: string, days: number): string {
	// Logs Explorer reads the query out of a `;`-separated path segment, not
	// the search string, so the newlines and quotes in it are percent-encoded
	// rather than left for the query string's own rules.
	const encoded = encodeURIComponent(query.trim());
	return `https://console.cloud.google.com/logs/query;query=${encoded};duration=P${days}D?project=${PROJECT}`;
}

/**
 * One metric's chart in Metrics Explorer. `pageState` is the console's own
 * serialisation and it normalises what it does not recognise, so this opens
 * the explorer on the right metric rather than on an exact chart.
 */
export function metricChart(metric: string): string {
	return `https://console.cloud.google.com/monitoring/metrics-explorer?project=${PROJECT}&pageState=${encodeURIComponent(
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

/** The API's own log lines, by the marker each signal is emitted under. */
export const API_LOG = `resource.type="cloud_run_revision"
resource.labels.service_name="beats-api"`;
