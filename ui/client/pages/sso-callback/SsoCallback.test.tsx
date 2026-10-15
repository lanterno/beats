/**
 * The page providers send the browser back to. What matters is what it
 * refuses: a callback this tab didn't start never reaches the API, since
 * finishing it would sign this browser into someone else's account.
 * `takeSsoState` is the real one, over jsdom's sessionStorage.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();
vi.mock("react-router", async () => {
	const actual = await vi.importActual<typeof import("react-router")>("react-router");
	return { ...actual, useNavigate: () => navigate };
});

vi.mock("@/features/auth", async () => {
	const actual = await vi.importActual<typeof import("@/features/auth")>("@/features/auth");
	return {
		...actual,
		completeSso: vi.fn(),
		getCurrentUser: vi.fn(() => Promise.resolve({ email: "a@x.com", display_name: "A" })),
		setSessionToken: vi.fn(),
		setUser: vi.fn(),
		useAuth: () => ({ isAuthenticated: false, isLoading: false }),
	};
});

import { completeSso, setSessionToken } from "@/features/auth";
import SsoCallback from "./SsoCallback";

const STATE_KEY = "beats.sso.state";

function arriveWith(query: string) {
	window.history.replaceState({}, "", `/auth/callback?${query}`);
	render(
		<MemoryRouter>
			<SsoCallback />
		</MemoryRouter>,
	);
}

beforeEach(() => sessionStorage.clear());
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe("SsoCallback", () => {
	it("finishes a sign-in this tab started, and opens the app", async () => {
		sessionStorage.setItem(STATE_KEY, "s1");
		vi.mocked(completeSso).mockResolvedValue({
			intent: "sign_in",
			provider: "google",
			token: "session",
			created: false,
		});
		arriveWith("code=c1&state=s1");

		await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/app", { replace: true }));
		expect(completeSso).toHaveBeenCalledWith("c1", "s1");
		expect(setSessionToken).toHaveBeenCalledWith("session");
		// The code doesn't stay in the address bar or the history.
		expect(window.location.search).toBe("");
	});

	it("returns a link to Settings", async () => {
		sessionStorage.setItem(STATE_KEY, "s1");
		vi.mocked(completeSso).mockResolvedValue({
			intent: "link",
			provider: "google",
			token: null,
			created: false,
		});
		arriveWith("code=c1&state=s1");

		await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/settings", { replace: true }));
		expect(setSessionToken).not.toHaveBeenCalled();
	});

	it("refuses a callback with another state, without asking the API", async () => {
		sessionStorage.setItem(STATE_KEY, "mine");
		arriveWith("code=theirs&state=theirs");

		expect(await screen.findByText(/wasn't started here/i)).toBeTruthy();
		expect(completeSso).not.toHaveBeenCalled();
	});

	it("refuses a callback when this tab started nothing", async () => {
		arriveWith("code=c1&state=s1");
		expect(await screen.findByText(/wasn't started here/i)).toBeTruthy();
		expect(completeSso).not.toHaveBeenCalled();
	});

	it("says a cancelled sign-in was cancelled", async () => {
		sessionStorage.setItem(STATE_KEY, "s1");
		arriveWith("error=access_denied&state=s1");
		expect(await screen.findByText(/cancelled/i)).toBeTruthy();
		expect(completeSso).not.toHaveBeenCalled();
	});

	it("shows the API's reason when it refuses", async () => {
		sessionStorage.setItem(STATE_KEY, "s1");
		vi.mocked(completeSso).mockRejectedValue(new Error("No account is linked to this identity."));
		arriveWith("code=c1&state=s1");
		expect(await screen.findByText(/No account is linked/i)).toBeTruthy();
		expect(screen.getByRole("link", { name: /Back to sign in/i })).toBeTruthy();
	});
});
