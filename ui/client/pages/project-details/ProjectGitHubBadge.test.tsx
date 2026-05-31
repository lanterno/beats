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
		useGitHubStatusMock.mockReturnValue({ data: { connected: false } });
	});
	afterEach(cleanup);

	it("renders an external GitHub link when connected and the repo is set", () => {
		useGitHubStatusMock.mockReturnValue({ data: { connected: true } });
		render(<ProjectGitHubBadge githubRepo="lanterno/beats" onConfigure={() => {}} />);
		const link = screen.getByRole("link", { name: /lanterno\/beats/ });
		expect(link).toHaveAttribute("href", "https://github.com/lanterno/beats");
		expect(link).toHaveAttribute("target", "_blank");
		expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
	});

	it("shows a 'Connect GitHub' button when the repo is set but OAuth isn't connected", async () => {
		const onConfigure = vi.fn();
		render(<ProjectGitHubBadge githubRepo="lanterno/beats" onConfigure={onConfigure} />);
		const btn = screen.getByRole("button", { name: /Connect GitHub/ });
		await userEvent.click(btn);
		expect(onConfigure).toHaveBeenCalled();
	});

	it("shows a 'Link a repo' button when the project has no github_repo", async () => {
		useGitHubStatusMock.mockReturnValue({ data: { connected: true } });
		const onConfigure = vi.fn();
		render(<ProjectGitHubBadge githubRepo={null} onConfigure={onConfigure} />);
		const btn = screen.getByRole("button", { name: /Link a repo/ });
		await userEvent.click(btn);
		expect(onConfigure).toHaveBeenCalled();
	});

	it("treats whitespace-only github_repo as unset", () => {
		useGitHubStatusMock.mockReturnValue({ data: { connected: true } });
		render(<ProjectGitHubBadge githubRepo="   " onConfigure={() => {}} />);
		expect(screen.getByRole("button", { name: /Link a repo/ })).toBeInTheDocument();
	});
});
