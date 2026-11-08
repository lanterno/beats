import { describe, expect, it } from "vitest";
import { OperatorApiError } from "@/shared/api/client";
import { plainMessage } from "./errors";

describe("plainMessage", () => {
	it("keeps the API's own words when they are already written for a person", () => {
		const error = new OperatorApiError(
			409,
			"An erasure is queued for this account; cancel the job instead",
			"ERASURE_QUEUED",
		);
		expect(plainMessage(error)).toBe(
			"An erasure is queued for this account; cancel the job instead",
		);
	});

	it("never shows a server failure's raw text", () => {
		const error = new OperatorApiError(500, "Request failed: Internal Server Error");
		expect(plainMessage(error)).not.toContain("Request failed");
	});

	it("never shows a raw exception when nothing answered", () => {
		expect(plainMessage(new TypeError("Failed to fetch"))).not.toContain("Failed to fetch");
	});
});
