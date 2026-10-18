/**
 * The report page tells a report from an error by parsing the body, so a
 * dead link's 404 envelope must never pass for a report. Key sets are not
 * pinned here (z.object strips unknown keys); the API's are, in pytest.
 */
import { describe, expect, it } from "vitest";
import { PublicReportSchema } from "./schema";

describe("PublicReportSchema", () => {
	it("a 404 body is not a report", () => {
		const notFound = { detail: "This report link isn't valid.", code: "REPORT_NOT_FOUND" };
		expect(PublicReportSchema.safeParse(notFound).success).toBe(false);
	});
});
