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
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
	const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
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
import { getLoginOptions, registerStart, verifyLogin, verifyRegistration } from "../api/authApi";
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
			expect(screen.queryByText("Beats")).not.toBeInTheDocument();
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
			// The X button has no aria-label; find it via the lucide X icon being inside.
			const closeBtns = screen
				.getAllByRole("button")
				.filter((b) => b.querySelector("svg") && b.className.includes("absolute"));
			expect(closeBtns.length).toBe(1);
			await userEvent.click(closeBtns[0]);
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
});
