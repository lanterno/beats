/**
 * The pairing code in Settings → Daemon.
 *
 * A code is worth showing only while the API will still take it. The page
 * clears it at a wall-clock deadline, and must do so even when the tab's
 * timers never got the chance to fire: a laptop that slept through the
 * deadline comes back to a hidden-then-visible tab, not to a ticking one.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { get, post, del, toastSuccess, toastError } = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	del: vi.fn(),
	toastSuccess: vi.fn(),
	toastError: vi.fn(),
}));

vi.mock("@/shared/api", async () => {
	const actual = await vi.importActual<typeof import("@/shared/api")>("@/shared/api");
	return { ...actual, get, post, del };
});
vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError } }));

import { DaemonSection } from "./DaemonSection";

/** Let the mocked request resolve and React commit what it set. */
async function flush() {
	await act(() => vi.advanceTimersByTimeAsync(0));
}

async function showCode() {
	render(<DaemonSection />);
	await flush();
	fireEvent.click(screen.getByRole("button", { name: "Pair new device" }));
	await flush();
	expect(screen.getByText("ABC234")).toBeInTheDocument();
}

beforeEach(() => {
	vi.clearAllMocks();
	vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "Date"] });
	get.mockResolvedValue([]);
	post.mockResolvedValue({ code: "ABC234", expires_in_seconds: 300 });
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
});

describe("DaemonSection pairing code", () => {
	it("clears the code at its deadline and offers a new one", async () => {
		await showCode();

		await act(() => vi.advanceTimersByTimeAsync(299_000));
		expect(screen.getByText("ABC234")).toBeInTheDocument();

		await act(() => vi.advanceTimersByTimeAsync(1_000));
		expect(screen.queryByText("ABC234")).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Pair new device" })).toBeInTheDocument();
	});

	it("clears a code that expired while the tab slept, when the tab comes back", async () => {
		await showCode();

		// The clock moves past the deadline but no timer fires, as when the
		// machine sleeps or the browser throttles a hidden tab.
		vi.setSystemTime(Date.now() + 301_000);
		act(() => {
			document.dispatchEvent(new Event("visibilitychange"));
		});

		expect(screen.queryByText("ABC234")).not.toBeInTheDocument();
	});
});
