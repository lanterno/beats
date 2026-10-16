import { describe, expect, it } from "vitest";
import { pairingQrPayload } from "./pairingQr";

describe("pairingQrPayload", () => {
	// The companion parses this same literal in companion/test/qr_pairing_test.dart.
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
});
