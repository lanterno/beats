import { describe, expect, it } from "vitest";
import { pairingQrPayload } from "./pairingQr";

describe("pairingQrPayload", () => {
	// companion/test/qr_pairing_test.dart is meant to parse this same literal.
	// A change here is a change to what every phone has to read.
	it("is the JSON the companion parses", () => {
		expect(
			pairingQrPayload({
				code: "ABC234",
				api: "https://api.lifepete.com",
				web: "https://lifepete.com",
			}),
		).toBe('{"code":"ABC234","api":"https://api.lifepete.com","web":"https://lifepete.com"}');
	});

	// The dev server, or a local build, pointed at a remote API: the QR still
	// pairs, but the phone must not save this machine as its web address.
	it("leaves web out when the page is opened at a loopback origin", () => {
		expect(
			pairingQrPayload({
				code: "ABC234",
				api: "https://api.lifepete.com",
				web: "http://localhost:8080",
			}),
		).toBe('{"code":"ABC234","api":"https://api.lifepete.com"}');
	});
});
