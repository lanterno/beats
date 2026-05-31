import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectGitHubBadge } from "./ProjectGitHubBadge";

const useGitHubStatusMock = vi.fn();

vi.mock("@/entities/github", () => ({
	useGitHubStatus: () => useGitHubStatusMock(),
}));

describe("ProjectGitHubBadge", () => {
	beforeEach(() => {
		useGitHubStatusMock.mockReturnValue({ data: { connected: false }, isPending: false });
	});
	afterEach(cleanup);

	it("renders an external GitHub link when connected and the repo is set", () => {
		useGitHubStatusMock.mockReturnValue({ data: { connected: true }, isPending: false });
		render(
			<ProjectGitHubBadge
				githubRepo="lanterno/beats"
				onConfigureRepo={() => {}}
				onConnectGitHub={() => {}}
			/>,
		);
		const link = screen.getByRole("link", { name: /lanterno\/beats/ });
		expect(link).toHaveAttribute("href", "https://github.com/lanterno/beats");
		expect(link).toHaveAttribute("target", "_blank");
		expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
	});

	it("Connect GitHub click routes to onConnectGitHub, NOT onConfigureRepo", async () => {
		// The pre-FF.2 bug: both buttons fired the same callback, which opened
		// the settings drawer on the *name* field — promising OAuth the
		// drawer couldn't deliver.
		const onConfigureRepo = vi.fn();
		const onConnectGitHub = vi.fn();
		render(
			<ProjectGitHubBadge
				githubRepo="lanterno/beats"
				onConfigureRepo={onConfigureRepo}
				onConnectGitHub={onConnectGitHub}
			/>,
		);
		await userEvent.click(screen.getByRole("button", { name: /Connect GitHub/ }));
		expect(onConnectGitHub).toHaveBeenCalledTimes(1);
		expect(onConfigureRepo).not.toHaveBeenCalled();
	});

	it("Link-a-repo click routes to onConfigureRepo (focuses the repo input)", async () => {
		useGitHubStatusMock.mockReturnValue({ data: { connected: true }, isPending: false });
		const onConfigureRepo = vi.fn();
		const onConnectGitHub = vi.fn();
		render(
			<ProjectGitHubBadge
				githubRepo={null}
				onConfigureRepo={onConfigureRepo}
				onConnectGitHub={onConnectGitHub}
			/>,
		);
		await userEvent.click(screen.getByRole("button", { name: /Link a repo/ }));
		expect(onConfigureRepo).toHaveBeenCalledTimes(1);
		expect(onConnectGitHub).not.toHaveBeenCalled();
	});

	it("treats whitespace-only github_repo as unset", () => {
		useGitHubStatusMock.mockReturnValue({ data: { connected: true }, isPending: false });
		render(
			<ProjectGitHubBadge githubRepo="   " onConfigureRepo={() => {}} onConnectGitHub={() => {}} />,
		);
		expect(screen.getByRole("button", { name: /Link a repo/ })).toBeInTheDocument();
	});

	it("suppresses the dashed 'Connect GitHub' CTA while the status query is loading for a project with a repo", () => {
		// Hard reload on a project with a linked repo + OAuth connected:
		// status is undefined for a tick. The pre-FF.2 badge flashed
		// "Connect GitHub" before flipping to the link. Now it shows a
		// neutral placeholder instead.
		useGitHubStatusMock.mockReturnValue({ data: undefined, isPending: true });
		render(
			<ProjectGitHubBadge
				githubRepo="lanterno/beats"
				onConfigureRepo={() => {}}
				onConnectGitHub={() => {}}
			/>,
		);
		expect(screen.queryByRole("button", { name: /Connect GitHub/ })).not.toBeInTheDocument();
		expect(screen.queryByRole("link", { name: /lanterno\/beats/ })).not.toBeInTheDocument();
		// Placeholder still visually echoes the repo name so the layout
		// doesn't pop when the query resolves.
		expect(screen.getByText("lanterno/beats")).toBeInTheDocument();
	});
});
