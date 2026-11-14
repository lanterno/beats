import { describe, expect, it } from "vitest";
import { handedOver, handOver } from "./handover";

const KEY = "9f2c4e1a7b3d5f60";

describe("handOver", () => {
	it("puts the key in navigation state and only its name in the URL", () => {
		const link = handOver("/review/control.set/signups", { network: KEY });
		expect(link.to).toEqual({
			pathname: "/review/control.set/signups",
			search: "?carried=network",
		});
		expect(JSON.stringify(link.to)).not.toContain(KEY);
		expect(link.state).toEqual({ carried: { network: KEY } });
	});
});

describe("handedOver", () => {
	const search = new URLSearchParams("?carried=network");

	it("reads what the URL names from navigation state", () => {
		expect(handedOver(search, { carried: { network: KEY } })).toEqual({ network: KEY });
	});

	// A new tab or a copied link keeps the URL and loses the state. Read as
	// nothing handed over, the page would offer the act for everyone.
	it("is null when what the URL names did not arrive", () => {
		expect(handedOver(search, null)).toBeNull();
		expect(handedOver(search, { carried: {} })).toBeNull();
		expect(handedOver(search, { carried: { network: "" } })).toBeNull();
	});

	it("reads nothing the URL does not name", () => {
		expect(handedOver(new URLSearchParams(), { carried: { network: KEY } })).toEqual({});
	});

	it("takes the round trip", () => {
		const link = handOver("/review/control.clear/signups", { network: KEY });
		expect(handedOver(new URLSearchParams(link.to.search), link.state)).toEqual({ network: KEY });
	});
});
