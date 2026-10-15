/**
 * Tests for AuthModal — the WebAuthn login + registration entry point.
 *
 * Pin the contract that matters: mode switching, the
 * NotAllowedError-as-cancellation friendly-copy carve-out, the
 * unsupported-browser fallback, and Escape/backdrop dismissal. Skips
 * the actual WebAuthn ceremony — we mock @simplewebauthn/browser
 * because exercising it would require a synthetic authenticator and
 * isn't what these tests are about.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();
vi.mock("react-router", async () => {
	const actual = await vi.importActual<typeof import("react-router")>("react-router");
	return { ...actual, useNavigate: () => navigate };
});

vi.mock("@simplewebauthn/browser", () => ({
	browserSupportsWebAuthn: vi.fn(() => true),
	startRegistration: vi.fn(),
	startAuthentication: vi.fn(),
}));

vi.mock("../api/authApi", () => ({
	registerStart: vi.fn(),
	verifyRegistration: vi.fn(),
	getLoginOptions: vi.fn(),
	verifyLogin: vi.fn(),
	getCurrentUser: vi.fn(() => Promise.resolve({ email: "test@example.com", display_name: "Test" })),
	// No providers by default, matching a deployment without single sign-on —
	// every test outside the SSO block asserts the single-door UI.
	getSsoProviders: vi.fn(() => Promise.resolve([])),
	startSsoSignIn: vi.fn(),
}));

vi.mock("../stores/authStore", () => ({
	setSessionToken: vi.fn(),
	setUser: vi.fn(),
}));

import {
	browserSupportsWebAuthn,
	startAuthentication,
	startRegistration,
} from "@simplewebauthn/browser";
import { APP_NAME } from "@/shared/config";
import {
	getLoginOptions,
	getSsoProviders,
	registerStart,
	startSsoSignIn,
	verifyLogin,
	verifyRegistration,
} from "../api/authApi";
import { setSessionToken, setUser } from "../stores/authStore";
import AuthModal from "./AuthModal";

function renderModal(props: Partial<React.ComponentProps<typeof AuthModal>> = {}) {
	const onClose = props.onClose ?? vi.fn();
	const utils = render(
		<MemoryRouter>
			<AuthModal open={props.open ?? true} onClose={onClose} initialMode={props.initialMode} />
		</MemoryRouter>,
	);
	return { ...utils, onClose };
}

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
	(browserSupportsWebAuthn as ReturnType<typeof vi.fn>).mockReturnValue(true);
});

describe("AuthModal", () => {
	describe("visibility", () => {
		it("renders nothing when open is false", () => {
			renderModal({ open: false });
			expect(screen.queryByText(APP_NAME)).not.toBeInTheDocument();
		});

		it("renders the login mode by default", () => {
			renderModal();
			expect(screen.getByText("Sign in with your passkey")).toBeInTheDocument();
			expect(screen.getByRole("button", { name: /Sign In with Passkey/i })).toBeInTheDocument();
		});

		it("renders the register-email mode when initialMode is register-email", () => {
			renderModal({ initialMode: "register-email" });
			expect(screen.getByText("Create your account")).toBeInTheDocument();
			expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
		});
	});

	describe("browser support fallback", () => {
		it("shows the unsupported-browser copy when WebAuthn is unavailable", () => {
			(browserSupportsWebAuthn as ReturnType<typeof vi.fn>).mockReturnValue(false);
			renderModal();
			expect(screen.getByText("Browser Not Supported")).toBeInTheDocument();
			// And the auth UI is hidden — no sign-in button rendered.
			expect(
				screen.queryByRole("button", { name: /Sign In with Passkey/i }),
			).not.toBeInTheDocument();
		});
	});

	describe("mode switching", () => {
		it("switches from login to register-email via the bottom link", async () => {
			renderModal();
			const switchBtn = screen.getByRole("button", { name: /Create an account/i });
			await userEvent.click(switchBtn);
			expect(screen.getByText("Create your account")).toBeInTheDocument();
		});

		it("switches back to login from register-email", async () => {
			renderModal({ initialMode: "register-email" });
			const switchBtn = screen.getByRole("button", { name: /Already have a passkey/i });
			await userEvent.click(switchBtn);
			expect(screen.getByText("Sign in with your passkey")).toBeInTheDocument();
		});
	});

	describe("login flow", () => {
		it("calls verifyLogin and navigates to /app on success", async () => {
			(getLoginOptions as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "x" },
			});
			(startAuthentication as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "cred-1" });
			(verifyLogin as ReturnType<typeof vi.fn>).mockResolvedValue({
				verified: true,
				token: "jwt-abc",
			});

			renderModal();
			await userEvent.click(screen.getByRole("button", { name: /Sign In with Passkey/i }));

			// Wait for the side effects to settle.
			await vi.waitFor(() => {
				expect(setSessionToken).toHaveBeenCalledWith("jwt-abc");
				expect(navigate).toHaveBeenCalledWith("/app", { replace: true });
			});
		});

		it("shows the cancellation copy on a NotAllowedError (user cancelled)", async () => {
			(getLoginOptions as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "x" },
			});
			const cancelErr = new Error("aborted");
			cancelErr.name = "NotAllowedError";
			(startAuthentication as ReturnType<typeof vi.fn>).mockRejectedValue(cancelErr);

			renderModal();
			await userEvent.click(screen.getByRole("button", { name: /Sign In with Passkey/i }));

			expect(
				await screen.findByText("Authentication was cancelled or timed out."),
			).toBeInTheDocument();
			// The friendly copy must NOT include the raw error message.
			expect(screen.queryByText(/aborted/i)).not.toBeInTheDocument();
			// And we did NOT navigate.
			expect(navigate).not.toHaveBeenCalled();
		});

		it("shows the verified=false copy when the server rejects the credential", async () => {
			(getLoginOptions as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "x" },
			});
			(startAuthentication as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "cred-1" });
			(verifyLogin as ReturnType<typeof vi.fn>).mockResolvedValue({
				verified: false,
				token: "",
			});

			renderModal();
			await userEvent.click(screen.getByRole("button", { name: /Sign In with Passkey/i }));

			expect(
				await screen.findByText("Authentication failed. Please try again."),
			).toBeInTheDocument();
			expect(setSessionToken).not.toHaveBeenCalled();
			expect(navigate).not.toHaveBeenCalled();
		});
	});

	describe("registration flow", () => {
		it("submitting the email form advances to the passkey step", async () => {
			(registerStart as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "y" },
				user_id: "u1",
			});

			renderModal({ initialMode: "register-email" });
			await userEvent.type(screen.getByLabelText(/Email/i), "new@example.com");
			await userEvent.click(screen.getByRole("button", { name: /Continue/i }));

			expect(await screen.findByText("Set up your passkey")).toBeInTheDocument();
			expect(registerStart).toHaveBeenCalledWith("new@example.com", undefined);
		});

		it("forwards an optional display name when provided", async () => {
			(registerStart as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "y" },
				user_id: "u1",
			});

			renderModal({ initialMode: "register-email" });
			await userEvent.type(screen.getByLabelText(/Email/i), "ada@example.com");
			await userEvent.type(screen.getByLabelText(/Display name/i), "Ada");
			await userEvent.click(screen.getByRole("button", { name: /Continue/i }));

			await vi.waitFor(() => {
				expect(registerStart).toHaveBeenCalledWith("ada@example.com", "Ada");
			});
		});

		it("registration verify success calls setSessionToken and navigates", async () => {
			(registerStart as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "y" },
				user_id: "u1",
			});
			(startRegistration as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "cred-2" });
			(verifyRegistration as ReturnType<typeof vi.fn>).mockResolvedValue({
				verified: true,
				token: "jwt-new",
			});

			renderModal({ initialMode: "register-email" });
			await userEvent.type(screen.getByLabelText(/Email/i), "new@example.com");
			await userEvent.click(screen.getByRole("button", { name: /Continue/i }));

			// Now in passkey step; click Set Up Passkey.
			const setUpBtn = await screen.findByRole("button", { name: /Set Up Passkey/i });
			await userEvent.click(setUpBtn);

			await vi.waitFor(() => {
				expect(setSessionToken).toHaveBeenCalledWith("jwt-new");
				expect(navigate).toHaveBeenCalledWith("/app", { replace: true });
			});
		});

		it("registration NotAllowedError shows the friendly cancellation copy", async () => {
			(registerStart as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "y" },
				user_id: "u1",
			});
			const cancelErr = new Error("aborted");
			cancelErr.name = "NotAllowedError";
			(startRegistration as ReturnType<typeof vi.fn>).mockRejectedValue(cancelErr);

			renderModal({ initialMode: "register-email" });
			await userEvent.type(screen.getByLabelText(/Email/i), "new@example.com");
			await userEvent.click(screen.getByRole("button", { name: /Continue/i }));

			const setUpBtn = await screen.findByRole("button", { name: /Set Up Passkey/i });
			await userEvent.click(setUpBtn);

			expect(
				await screen.findByText("Registration was cancelled or timed out."),
			).toBeInTheDocument();
		});

		it("the email Continue button is disabled until an email is typed", () => {
			renderModal({ initialMode: "register-email" });
			const btn = screen.getByRole("button", { name: /Continue/i });
			expect(btn).toBeDisabled();
		});
	});

	describe("dismissal", () => {
		it("calls onClose when Escape is pressed", () => {
			const { onClose } = renderModal();
			fireEvent.keyDown(document, { key: "Escape" });
			expect(onClose).toHaveBeenCalled();
		});

		it("calls onClose when the close (X) button is clicked", async () => {
			const { onClose } = renderModal();
			await userEvent.click(screen.getByRole("button", { name: "Close dialog" }));
			expect(onClose).toHaveBeenCalled();
		});

		it("setUser is invoked after a successful login (best-effort, no await)", async () => {
			(getLoginOptions as ReturnType<typeof vi.fn>).mockResolvedValue({
				options: { challenge: "x" },
			});
			(startAuthentication as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "cred-1" });
			(verifyLogin as ReturnType<typeof vi.fn>).mockResolvedValue({
				verified: true,
				token: "jwt-abc",
			});

			renderModal();
			await userEvent.click(screen.getByRole("button", { name: /Sign In with Passkey/i }));

			await vi.waitFor(() => {
				// setUser is called from the .then() of getCurrentUser, which is
				// fire-and-forget — the user lands on /app even if it's slow.
				expect(setUser).toHaveBeenCalledWith({
					email: "test@example.com",
					displayName: "Test",
				});
			});
		});
	});

	describe("re-open resets state", () => {
		it("clears the email field when the modal is reopened", () => {
			const onClose = vi.fn();
			const { rerender } = render(
				<MemoryRouter>
					<AuthModal open={true} onClose={onClose} initialMode="register-email" />
				</MemoryRouter>,
			);
			const input = screen.getByLabelText(/Email/i) as HTMLInputElement;
			fireEvent.change(input, { target: { value: "stale@example.com" } });
			expect(input.value).toBe("stale@example.com");

			// Close, then re-open. The reset effect runs on every open=true
			// transition (including remounts via key change), so the email
			// field should come back blank.
			rerender(
				<MemoryRouter>
					<AuthModal open={false} onClose={onClose} initialMode="register-email" />
				</MemoryRouter>,
			);
			rerender(
				<MemoryRouter>
					<AuthModal open={true} onClose={onClose} initialMode="register-email" />
				</MemoryRouter>,
			);

			expect((screen.getByLabelText(/Email/i) as HTMLInputElement).value).toBe("");
		});
	});

	describe("single sign-on — the second door", () => {
		const providers = [
			{ id: "google", name: "Google" },
			{ id: "work", name: "Work" },
		];

		it("shows no provider buttons when none is set up", async () => {
			renderModal({ initialMode: "login" });
			// Wait for the fetch to settle, so this can't pass merely by being early.
			await vi.waitFor(() => expect(getSsoProviders).toHaveBeenCalled());
			expect(screen.queryByRole("button", { name: /Continue with/i })).toBeNull();
		});

		it("offers one button per provider, alongside the passkey login", async () => {
			vi.mocked(getSsoProviders).mockResolvedValue(providers);
			renderModal({ initialMode: "login" });

			expect(await screen.findByRole("button", { name: /Continue with Google/i })).toBeTruthy();
			expect(screen.getByRole("button", { name: /Continue with Work/i })).toBeTruthy();
			// Both doors stay open.
			expect(screen.getByRole("button", { name: /Sign In with Passkey/i })).toBeTruthy();
		});

		it("starts the sign-in with the provider that was clicked", async () => {
			vi.mocked(getSsoProviders).mockResolvedValue(providers);
			vi.mocked(startSsoSignIn).mockReturnValue(new Promise(() => {}));
			renderModal({ initialMode: "login" });

			await userEvent.click(await screen.findByRole("button", { name: /Continue with Work/i }));
			expect(startSsoSignIn).toHaveBeenCalledWith("work");
		});

		it("says so when the provider can't be reached, and lets you try again", async () => {
			vi.mocked(getSsoProviders).mockResolvedValue(providers);
			vi.mocked(startSsoSignIn).mockRejectedValue(new Error("Google can't be reached right now."));
			renderModal({ initialMode: "login" });

			const button = await screen.findByRole("button", { name: /Continue with Google/i });
			await userEvent.click(button);
			expect(await screen.findByText(/can't be reached/i)).toBeTruthy();
			expect((button as HTMLButtonElement).disabled).toBe(false);
		});
	});
});
