import { beforeEach, describe, expect, it } from "vitest";
import { clearPickerRecents, readPickerRecents, recordPickerRecent } from "./pickerRecents";

const USER = "alice@example.com";

describe("pickerRecents", () => {
	beforeEach(() => {
		window.localStorage.clear();
	});

	it("returns [] when no user is provided (logged-out)", () => {
		expect(readPickerRecents(null)).toEqual([]);
		expect(readPickerRecents(undefined)).toEqual([]);
	});

	it("returns [] for users with no stored recents", () => {
		expect(readPickerRecents(USER)).toEqual([]);
	});

	it("records selections newest-first", () => {
		recordPickerRecent(USER, "a");
		recordPickerRecent(USER, "b");
		recordPickerRecent(USER, "c");
		expect(readPickerRecents(USER)).toEqual(["c", "b", "a"]);
	});

	it("dedupes — re-selecting an id moves it to the front", () => {
		recordPickerRecent(USER, "a");
		recordPickerRecent(USER, "b");
		recordPickerRecent(USER, "a");
		expect(readPickerRecents(USER)).toEqual(["a", "b"]);
	});

	it("caps the recents list at 8 entries", () => {
		for (const id of ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]) {
			recordPickerRecent(USER, id);
		}
		const recents = readPickerRecents(USER);
		expect(recents).toHaveLength(8);
		expect(recents[0]).toBe("10");
	});

	it("scopes by user — recents written for one user are invisible to another", () => {
		recordPickerRecent(USER, "a");
		recordPickerRecent("bob@example.com", "b");
		expect(readPickerRecents(USER)).toEqual(["a"]);
		expect(readPickerRecents("bob@example.com")).toEqual(["b"]);
	});

	it("recovers from corrupt storage by returning []", () => {
		window.localStorage.setItem("beats:project-picker-recents:v1:alice@example.com", "{not json");
		expect(readPickerRecents(USER)).toEqual([]);
	});

	it("clearPickerRecents wipes only the targeted user", () => {
		recordPickerRecent(USER, "a");
		recordPickerRecent("bob@example.com", "b");
		clearPickerRecents(USER);
		expect(readPickerRecents(USER)).toEqual([]);
		expect(readPickerRecents("bob@example.com")).toEqual(["b"]);
	});
});
