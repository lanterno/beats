/**
 * Tests for FlowFilterChips. The component is rendered above every
 * Flow* card on the Insights page when any chip filter is active, so
 * its dismiss buttons are how users routinely undo a filter selection.
 *
 * Locks in:
 * - Each pill renders only when its filter prop is set.
 * - The dismiss button calls the right onClear (one regression here
 *   would silently clear the wrong axis).
 * - The "↓ csv" link is always present, even with no filters set
 *   (the parent only mounts the component when a chip is active, but
 *   we don't want the component to silently break if it's reused
 *   somewhere else without filters).
 * - The CSV href maps camelCase props to snake_case API params
 *   (same regression class as fetchFlowWindows.test.ts but at the
 *   download-link layer).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FlowFilterChips, flowWindowsCsvHref } from "./FlowFilterChips";

afterEach(cleanup);

const noopHandlers = {
	onClearRepo: () => {},
	onClearLanguage: () => {},
	onClearBundleId: () => {},
};

describe("FlowFilterChips", () => {
	it("renders only the pills whose filter prop is set", () => {
		render(<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} />);

		// The dismiss buttons are uniquely keyed by their aria-label,
		// which is the cleanest way to assert which pills mounted.
		expect(screen.getByLabelText("Clear repo filter")).toBeInTheDocument();
		expect(screen.queryByLabelText("Clear language filter")).not.toBeInTheDocument();
		expect(screen.queryByLabelText("Clear app filter")).not.toBeInTheDocument();
	});

	it("calls onClearRepo when the repo pill's clear button is clicked", () => {
		const onClearRepo = vi.fn();
		render(
			<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} onClearRepo={onClearRepo} />,
		);

		fireEvent.click(screen.getByLabelText("Clear repo filter"));

		expect(onClearRepo).toHaveBeenCalledOnce();
	});

	it("calls onClearLanguage when the language pill's clear button is clicked", () => {
		const onClearLanguage = vi.fn();
		render(<FlowFilterChips language="go" {...noopHandlers} onClearLanguage={onClearLanguage} />);

		fireEvent.click(screen.getByLabelText("Clear language filter"));

		expect(onClearLanguage).toHaveBeenCalledOnce();
	});

	it("calls onClearBundleId when the app pill's clear button is clicked", () => {
		const onClearBundleId = vi.fn();
		render(
			<FlowFilterChips
				bundleId="com.microsoft.VSCode"
				{...noopHandlers}
				onClearBundleId={onClearBundleId}
			/>,
		);

		fireEvent.click(screen.getByLabelText("Clear app filter"));

		expect(onClearBundleId).toHaveBeenCalledOnce();
	});

	it("does not cross-call: clicking repo's clear must not invoke onClearLanguage", () => {
		const onClearRepo = vi.fn();
		const onClearLanguage = vi.fn();
		render(
			<FlowFilterChips
				repo="/Users/me/code/beats"
				language="go"
				{...noopHandlers}
				onClearRepo={onClearRepo}
				onClearLanguage={onClearLanguage}
			/>,
		);

		fireEvent.click(screen.getByLabelText("Clear repo filter"));

		expect(onClearRepo).toHaveBeenCalledOnce();
		expect(onClearLanguage).not.toHaveBeenCalled();
	});

	it("renders the ↓ csv download button", () => {
		render(<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} />);
		expect(screen.getByRole("button", { name: /↓ csv/ })).toBeInTheDocument();
	});

	it("shortens the repo display to the last two path segments", () => {
		render(<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} />);
		expect(screen.getByText("code/beats")).toBeInTheDocument();
		// The full path should still be available via the title attribute
		// for the user who hovers.
		expect(screen.getByTitle("/Users/me/code/beats")).toBeInTheDocument();
	});

	it("shortens the bundle display to the last reverse-DNS segment", () => {
		render(<FlowFilterChips bundleId="com.microsoft.VSCode" {...noopHandlers} />);
		expect(screen.getByText("VSCode")).toBeInTheDocument();
		expect(screen.getByTitle("com.microsoft.VSCode")).toBeInTheDocument();
	});

	describe("copy-link button", () => {
		const writeText = vi.fn();

		beforeEach(() => {
			writeText.mockReset();
			// jsdom doesn't ship navigator.clipboard by default — stub
			// only the writeText path the component uses.
			Object.defineProperty(navigator, "clipboard", {
				value: { writeText },
				configurable: true,
			});
			// Pin the URL so the assertion below isn't dependent on
			// whatever the test runner left behind.
			window.history.replaceState({}, "", "/insights?repo=foo&language=go");
		});

		it("renders a copy-link button", () => {
			render(<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} />);
			expect(screen.getByRole("button", { name: /copy link/ })).toBeInTheDocument();
		});

		it("writes the current URL to the clipboard on click", async () => {
			writeText.mockResolvedValueOnce(undefined);
			render(<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} />);

			fireEvent.click(screen.getByRole("button", { name: /copy link/ }));

			await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
			expect(writeText.mock.calls[0][0]).toContain("?repo=foo&language=go");
		});

		it("flips the label to '✓ copied' for visual confirmation", async () => {
			writeText.mockResolvedValueOnce(undefined);
			render(<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} />);

			fireEvent.click(screen.getByRole("button", { name: /copy link/ }));

			await waitFor(() =>
				expect(screen.getByRole("button", { name: /✓ copied/ })).toBeInTheDocument(),
			);
		});

		it("silently swallows clipboard errors (insecure context, denied perms)", async () => {
			// http (not https) browsers reject writeText. Component
			// should NOT throw — user falls back to copying the
			// address bar manually.
			writeText.mockRejectedValueOnce(new Error("not allowed"));
			render(<FlowFilterChips repo="/Users/me/code/beats" {...noopHandlers} />);

			fireEvent.click(screen.getByRole("button", { name: /copy link/ }));

			// Wait a tick to let the rejected promise settle. Component
			// stays in "copy link" state since the success branch never
			// runs.
			await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
			expect(screen.queryByRole("button", { name: /✓ copied/ })).not.toBeInTheDocument();
			expect(screen.getByRole("button", { name: /copy link/ })).toBeInTheDocument();
		});
	});
});

describe("flowWindowsCsvHref", () => {
	it("returns the bare URL when no filters are set", () => {
		expect(flowWindowsCsvHref({})).toBe("/api/signals/flow-windows.csv");
	});

	it("maps camelCase props to snake_case API query params", () => {
		const href = flowWindowsCsvHref({
			repo: "/Users/me/code/beats",
			language: "go",
			bundleId: "com.microsoft.VSCode",
		});
		const url = new URL(href, "http://localhost");
		expect(url.pathname).toBe("/api/signals/flow-windows.csv");
		expect(url.searchParams.get("editor_repo")).toBe("/Users/me/code/beats");
		expect(url.searchParams.get("editor_language")).toBe("go");
		expect(url.searchParams.get("bundle_id")).toBe("com.microsoft.VSCode");
	});

	it("omits empty filter params from the URL", () => {
		const href = flowWindowsCsvHref({ repo: "", language: undefined, bundleId: "" });
		expect(href).toBe("/api/signals/flow-windows.csv");
	});
});
