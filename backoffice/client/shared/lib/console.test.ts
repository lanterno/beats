import { describe, expect, it } from "vitest";
import { consoleLinks } from "./console";

describe("consoleLinks", () => {
	it("links into the project the operator API names, for the service it names", () => {
		const links = consoleLinks({ project: "p-123", api_service: "the-api" });
		expect(links?.monitoring).toBe(
			"https://console.cloud.google.com/monitoring/dashboards?project=p-123",
		);
		expect(links?.cloudRun).toBe("https://console.cloud.google.com/run?project=p-123");
		const log = decodeURIComponent(links?.apiLog("WRITE_LIMIT_REFUSED", 7) ?? "");
		expect(log).toContain('resource.labels.service_name="the-api"');
		expect(log).toContain('textPayload:"WRITE_LIMIT_REFUSED"');
		expect(log).toContain("duration=P7D?project=p-123");
		expect(decodeURIComponent(links?.apiMetric("import_bytes") ?? "")).toContain(
			"logging.googleapis.com/user/the-api/import_bytes",
		);
	});

	it("has nothing to link into off Google Cloud", () => {
		expect(consoleLinks({ project: null, api_service: "the-api" })).toBeNull();
	});
});
