/**
 * The projects tab's assignment flow: several members on one project show
 * as several chips; the dialog assigns everyone picked in one go; and when
 * there is nobody left to assign, the section says why instead of showing
 * nothing — the gap that used to read as "one user per project".
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Assignment, Member, OrgProject } from "@/entities/organisation";
import { ProjectsSection } from "./ProjectsSection";

const { state, assignMembers } = vi.hoisted(() => ({
	state: {
		projects: [] as unknown[],
		members: [] as unknown[],
	},
	assignMembers: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useOrgProjects: () => ({ data: state.projects, error: null }),
		useMembers: () => ({ data: state.members, error: null }),
		useAssignMembers: () => ({ isPending: false, mutateAsync: assignMembers }),
		useUnassignMember: () => ({ isPending: false, mutate: vi.fn() }),
	};
});

function member(userId: string, name: string): Member {
	return {
		userId,
		name,
		email: `${name.toLowerCase()}@acme.test`,
		role: "member",
		joinedAt: "2026-01-05T09:00:00Z",
	};
}

function assignment(userId: string, name: string): Assignment {
	return {
		userId,
		name,
		sharedFrom: "2026-02-01T09:00:00Z",
		assignedAt: "2026-02-01T09:00:00Z",
		hasContract: false,
	};
}

function project(members: Assignment[]): OrgProject {
	return { id: "p1", name: "Platform", archived: false, kind: "day_job", members };
}

function renderSection() {
	render(
		<MemoryRouter>
			<ProjectsSection organisationId="o1" />
		</MemoryRouter>,
	);
}

afterEach(() => {
	cleanup();
	assignMembers.mockClear();
});

describe("ProjectsSection", () => {
	it("shows a chip per member on the project", () => {
		state.members = [member("u1", "Nour"), member("u2", "Omar"), member("u3", "Lina")];
		state.projects = [project([assignment("u1", "Nour"), assignment("u2", "Omar")])];
		renderSection();

		expect(screen.getByText("Nour")).toBeInTheDocument();
		expect(screen.getByText("Omar")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Assign members to Platform" })).toBeInTheDocument();
	});

	it("assigns everyone picked in the dialog in one go", async () => {
		state.members = [member("u1", "Nour"), member("u2", "Omar"), member("u3", "Lina")];
		state.projects = [project([assignment("u1", "Nour")])];
		renderSection();

		fireEvent.click(screen.getByRole("button", { name: "Assign members to Platform" }));
		// Only the members not yet on it are offered.
		expect(screen.queryByRole("checkbox", { name: /Nour/ })).not.toBeInTheDocument();
		fireEvent.click(screen.getByRole("checkbox", { name: /Omar/ }));
		fireEvent.click(screen.getByRole("checkbox", { name: /Lina/ }));
		fireEvent.click(screen.getByRole("button", { name: "Assign 2 members" }));

		expect(assignMembers).toHaveBeenCalledWith({ projectId: "p1", userIds: ["u2", "u3"] });
		// The dialog closes once the assignments have landed.
		await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
	});

	it("says every member is on the project instead of hiding the control", () => {
		state.members = [member("u1", "Nour"), member("u2", "Omar")];
		state.projects = [project([assignment("u1", "Nour"), assignment("u2", "Omar")])];
		renderSection();

		expect(screen.queryByRole("button", { name: /Assign members/ })).not.toBeInTheDocument();
		expect(screen.getByText("Every member is on this project.")).toBeInTheDocument();
	});

	it("points the only member at inviting people", () => {
		state.members = [member("u1", "Nour")];
		state.projects = [project([assignment("u1", "Nour")])];
		renderSection();

		expect(screen.queryByRole("button", { name: /Assign members/ })).not.toBeInTheDocument();
		expect(screen.getByRole("link", { name: "invite people" })).toHaveAttribute(
			"href",
			"/?tab=people",
		);
	});
});
