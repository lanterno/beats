import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdvancedFields, type AdvancedFieldsValues, isValidGithubRepo } from "./AdvancedFields";

const EMPTY: AdvancedFieldsValues = {
	category: "",
	githubRepo: "",
	autostartRepos: [],
};

describe("isValidGithubRepo", () => {
	it("accepts empty (the field is optional)", () => {
		expect(isValidGithubRepo("")).toBe(true);
		expect(isValidGithubRepo("   ")).toBe(true);
	});

	it("accepts owner/repo", () => {
		expect(isValidGithubRepo("lanterno/beats")).toBe(true);
		expect(isValidGithubRepo("OWNER/repo.name")).toBe(true);
		expect(isValidGithubRepo("a/b")).toBe(true);
	});

	it("rejects anything without a single slash separator", () => {
		expect(isValidGithubRepo("just-a-string")).toBe(false);
		expect(isValidGithubRepo("https://github.com/lanterno/beats")).toBe(false);
		expect(isValidGithubRepo("two//slashes")).toBe(false);
		expect(isValidGithubRepo("trailing/slash/")).toBe(false);
	});
});

describe("AdvancedFields", () => {
	afterEach(cleanup);

	it("shows an inline error for an invalid github_repo and clears it when valid", async () => {
		const onChange = vi.fn();
		const { rerender } = render(
			<AdvancedFields values={{ ...EMPTY, githubRepo: "not-a-repo" }} onChange={onChange} />,
		);

		expect(screen.getByRole("alert")).toHaveTextContent(/owner\/repo/);

		// Fix the value via rerender — simulates the parent owning state.
		rerender(
			<AdvancedFields values={{ ...EMPTY, githubRepo: "lanterno/beats" }} onChange={onChange} />,
		);

		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});

	it("surfaces a connect-hint when GitHub OAuth is not connected", () => {
		render(<AdvancedFields values={EMPTY} onChange={vi.fn()} githubConnected={false} />);
		expect(screen.getByText(/Connect GitHub in Settings/)).toBeInTheDocument();
	});

	it("omits the connect-hint when GitHub is connected", () => {
		render(<AdvancedFields values={EMPTY} onChange={vi.fn()} githubConnected={true} />);
		expect(screen.queryByText(/Connect GitHub in Settings/)).not.toBeInTheDocument();
	});

	it("adds and removes autostart paths via the repeatable list", async () => {
		const onChange = vi.fn();
		const { rerender } = render(<AdvancedFields values={EMPTY} onChange={onChange} />);

		await userEvent.click(screen.getByRole("button", { name: /Add a path/ }));
		expect(onChange).toHaveBeenCalledWith({
			...EMPTY,
			autostartRepos: [""],
		});

		// Simulate the parent applying the new value, then type into the row.
		rerender(<AdvancedFields values={{ ...EMPTY, autostartRepos: [""] }} onChange={onChange} />);
		const input = screen.getByLabelText("Autostart path 1");
		await userEvent.type(input, "/Users/me/code/beats");

		// Removing the row clears it back to [].
		onChange.mockClear();
		await userEvent.click(screen.getByRole("button", { name: /Remove autostart path 1/ }));
		expect(onChange).toHaveBeenCalledWith({
			...EMPTY,
			autostartRepos: [],
		});
	});

	it("FF.4: deleting a middle autostart row keeps the trailing input's React identity", async () => {
		// Smoke-test the stable-key fix by spying on input.focus(): with index
		// keys, deleting row #1 unmounts row #2 and re-mounts what was row #3
		// in its place, blurring the focused input. With identity keys, the
		// trailing rows shift down by index but keep the same DOM node, so
		// activeElement stays put.
		const onChange = vi.fn();
		const initial: AdvancedFieldsValues = {
			...EMPTY,
			autostartRepos: ["/a", "/b", "/c"],
		};
		const { rerender } = render(<AdvancedFields values={initial} onChange={onChange} />);

		// Focus the third row's input — that's the one we want to keep alive.
		const thirdInput = screen.getByLabelText("Autostart path 3");
		thirdInput.focus();
		expect(document.activeElement).toBe(thirdInput);

		// User clicks Remove on row #1.
		await userEvent.click(screen.getByRole("button", { name: /Remove autostart path 1/ }));
		expect(onChange).toHaveBeenLastCalledWith({
			...EMPTY,
			autostartRepos: ["/b", "/c"],
		});

		// Parent applies the shrunken array.
		rerender(
			<AdvancedFields values={{ ...EMPTY, autostartRepos: ["/b", "/c"] }} onChange={onChange} />,
		);

		// The DOM node that holds "/c" is the SAME element we focused earlier.
		// Querying by its value is the cleanest assertion; activeElement is
		// preserved by React because the parent <div> key didn't change.
		const stillThere = screen.getByDisplayValue("/c");
		expect(stillThere).toBe(thirdInput);
	});

	it("seeds the category combobox with deduped + sorted suggestions", () => {
		render(
			<AdvancedFields
				values={EMPTY}
				onChange={vi.fn()}
				categorySuggestions={["writing", "coding", "writing"]}
			/>,
		);
		// The datalist is in the DOM; assert the unique sorted set is rendered.
		const options = document.querySelectorAll("datalist option");
		expect([...options].map((o) => o.getAttribute("value"))).toEqual(["coding", "writing"]);
	});
});
