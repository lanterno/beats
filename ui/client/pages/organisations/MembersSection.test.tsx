/**
 * Who gets which controls. The owner role moves only by an owner's hand, so
 * an admin is offered neither the role nor an owner's row; and the caller's
 * own row is read-only, found by the membership's `userId` rather than by
 * the address they joined under.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Member, OrgRole } from "@/entities/organisation";
import { MembersSection } from "./MembersSection";

const { state, idle } = vi.hoisted(() => ({
	state: { members: [] as unknown[] },
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useMembers: () => ({ data: state.members, error: null }),
		useSetMemberRole: idle,
		useRemoveMember: idle,
	};
});

function member(userId: string, name: string, role: OrgRole): Member {
	return {
		userId,
		name,
		email: `${name.toLowerCase()}@acme.test`,
		role,
		joinedAt: "2026-01-05T09:00:00Z",
	};
}

function renderSection(myRole: OrgRole, userId = "u-me") {
	render(
		<QueryClientProvider client={new QueryClient()}>
			<MembersSection organisationId="o1" role={myRole} userId={userId} />
		</QueryClientProvider>,
	);
}

afterEach(cleanup);

describe("MembersSection", () => {
	it("offers an admin no Owner role and no control over an owner's row", () => {
		state.members = [
			member("u-me", "Admin", "admin"),
			member("u1", "Olive", "owner"),
			member("u2", "Mem", "member"),
		];
		renderSection("admin");

		// The one role select is the plain member's; the owner row has none.
		expect(screen.queryByRole("combobox", { name: "Role of Olive" })).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Remove Olive" })).not.toBeInTheDocument();
		const roles = screen.getByRole("combobox", { name: "Role of Mem" });
		expect([...roles.querySelectorAll("option")].map((o) => o.textContent)).not.toContain("Owner");
	});

	it("gives an owner the Owner role and an owner's row", () => {
		state.members = [member("u-me", "Olive", "owner"), member("u1", "Pat", "owner")];
		renderSection("owner");

		const roles = screen.getByRole("combobox", { name: "Role of Pat" });
		expect([...roles.querySelectorAll("option")].map((o) => o.textContent)).toContain("Owner");
		expect(screen.getByRole("button", { name: "Remove Pat" })).toBeInTheDocument();
	});

	it("marks the caller's own row by id, not by the address they joined under", () => {
		// The same person, whose account has since changed its address.
		state.members = [member("u-me", "Me", "admin"), member("u2", "Other", "member")];
		renderSection("admin");

		expect(screen.getByText("(you)")).toBeInTheDocument();
		expect(screen.queryByRole("combobox", { name: "Role of Me" })).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Remove Me" })).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Remove Other" })).toBeInTheDocument();
	});
});
