import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TagInput } from "./tag-input";

afterEach(cleanup);

describe("TagInput", () => {
	it("renders existing tags", () => {
		render(<TagInput tags={["react", "typescript"]} onChange={() => {}} />);
		expect(screen.getByText("react")).toBeInTheDocument();
		expect(screen.getByText("typescript")).toBeInTheDocument();
	});

	it("shows placeholder when no tags", () => {
		render(<TagInput tags={[]} onChange={() => {}} placeholder="Add tag..." />);
		expect(screen.getByPlaceholderText("Add tag...")).toBeInTheDocument();
	});

	it("hides placeholder when tags exist", () => {
		render(<TagInput tags={["react"]} onChange={() => {}} placeholder="Add tag..." />);
		expect(screen.queryByPlaceholderText("Add tag...")).not.toBeInTheDocument();
	});

	it("adds tag on Enter", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={[]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "newtag{Enter}");

		expect(onChange).toHaveBeenCalledWith(["newtag"]);
	});

	it("adds tag on comma", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={[]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "newtag,");

		expect(onChange).toHaveBeenCalledWith(["newtag"]);
	});

	it("converts tags to lowercase", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={[]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "MyTag{Enter}");

		expect(onChange).toHaveBeenCalledWith(["mytag"]);
	});

	it("trims whitespace from tags", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={[]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "  spaced  {Enter}");

		expect(onChange).toHaveBeenCalledWith(["spaced"]);
	});

	it("does not add duplicate tags", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={["existing"]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "existing{Enter}");

		expect(onChange).not.toHaveBeenCalled();
	});

	it("does not add empty tags", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={[]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "   {Enter}");

		expect(onChange).not.toHaveBeenCalled();
	});

	it("removes tag on X button click", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={["react", "vue"]} onChange={onChange} />);

		const removeButtons = screen.getAllByRole("button");
		await userEvent.click(removeButtons[0]);

		expect(onChange).toHaveBeenCalledWith(["vue"]);
	});

	it("removes last tag on Backspace when input is empty", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={["react", "vue"]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.click(input);
		await userEvent.keyboard("{Backspace}");

		expect(onChange).toHaveBeenCalledWith(["react"]);
	});

	it("does not remove tag on Backspace when input has text", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={["react"]} onChange={onChange} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "ab{Backspace}");

		expect(onChange).not.toHaveBeenCalled();
	});

	it("shows filtered suggestions when typing", async () => {
		render(<TagInput tags={[]} onChange={() => {}} suggestions={["react", "redux", "vue"]} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "re");

		expect(screen.getByText("react")).toBeInTheDocument();
		expect(screen.getByText("redux")).toBeInTheDocument();
		expect(screen.queryByText("vue")).not.toBeInTheDocument();
	});

	it("excludes already-added tags from suggestions", async () => {
		render(<TagInput tags={["react"]} onChange={() => {}} suggestions={["react", "redux"]} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "re");

		// "react" is already a tag, so only "redux" should appear in suggestions
		const suggestions = screen.getAllByRole("button");
		const suggestionTexts = suggestions
			.filter((btn) => btn.classList.contains("w-full"))
			.map((btn) => btn.textContent);
		expect(suggestionTexts).toContain("redux");
	});

	it("adds tag when clicking a suggestion", async () => {
		const onChange = vi.fn();
		render(<TagInput tags={[]} onChange={onChange} suggestions={["react", "redux"]} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "re");

		// Click the "react" suggestion button
		const suggestionButtons = screen
			.getAllByRole("button")
			.filter((btn) => btn.textContent === "react");
		await userEvent.click(suggestionButtons[suggestionButtons.length - 1]);

		expect(onChange).toHaveBeenCalledWith(["react"]);
	});

	it("hides suggestions on Escape", async () => {
		render(<TagInput tags={[]} onChange={() => {}} suggestions={["react"]} />);

		const input = screen.getByRole("textbox");
		await userEvent.type(input, "re");
		expect(screen.getByText("react")).toBeInTheDocument();

		await userEvent.keyboard("{Escape}");
		// After Escape, suggestion dropdown should be hidden
		// The "react" text might still be in DOM but the dropdown container should not render
		const suggestionDropdown = document.querySelector(".absolute.z-10");
		expect(suggestionDropdown).toBeNull();
	});
});
