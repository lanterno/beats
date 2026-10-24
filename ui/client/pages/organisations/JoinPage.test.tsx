/**
 * The join page's answers: a closed invite says so in the page's words, a
 * live one offers Join, and an account already in the organisation is sent
 * to it rather than asked again.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { InvitePreview } from "@/entities/organisation";
import { ApiError } from "@/shared/api";
import JoinPage from "./JoinPage";

const { state, idle } = vi.hoisted(() => ({
	state: {
		preview: { data: undefined, error: null } as { data?: unknown; error: unknown },
	},
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useInvitePreview: () => state.preview,
		useJoinOrganisation: idle,
	};
});

const PREVIEW: InvitePreview = {
	organisation: { id: "o1", name: "Acme" },
	role: "member",
	requiresApproval: false,
	addressed: true,
	alreadyMember: false,
};

function renderPage() {
	render(
		<QueryClientProvider client={new QueryClient()}>
			<MemoryRouter initialEntries={["/organisations/join/tok"]}>
				<Routes>
					<Route path="/organisations/join/:token" element={<JoinPage />} />
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

afterEach(cleanup);

describe("JoinPage", () => {
	it("says a closed invite is no longer valid", () => {
		state.preview = { data: undefined, error: new ApiError(410, "Invite expired") };
		renderPage();
		expect(screen.getByRole("alert")).toHaveTextContent("This invite is no longer valid.");
	});

	it("says an unknown invite is not for this account", () => {
		state.preview = { data: undefined, error: new ApiError(404, "Not found") };
		renderPage();
		expect(screen.getByRole("alert")).toHaveTextContent(
			"This invite isn't for this account, or doesn't exist.",
		);
	});

	it("offers Join on a live invite", () => {
		state.preview = { data: PREVIEW, error: null };
		renderPage();
		expect(screen.getByText("You've been invited to join as a member.")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Join" })).toBeInTheDocument();
	});

	it("sends an account already in the organisation to it", () => {
		state.preview = { data: { ...PREVIEW, alreadyMember: true }, error: null };
		renderPage();
		expect(screen.getByText("You're already a member.")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "Open Acme" })).toHaveAttribute(
			"href",
			"/organisations/o1",
		);
		expect(screen.queryByRole("button", { name: "Join" })).not.toBeInTheDocument();
	});
});
