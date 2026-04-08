/**
 * TagInput Component
 * Freeform tag input with autocomplete from previously used tags.
 */

import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/shared/lib";

interface TagInputProps {
	tags: string[];
	onChange: (tags: string[]) => void;
	suggestions?: string[];
	placeholder?: string;
	className?: string;
}

export function TagInput({
	tags,
	onChange,
	suggestions = [],
	placeholder = "Add tag...",
	className,
}: TagInputProps) {
	const [input, setInput] = useState("");
	const [showSuggestions, setShowSuggestions] = useState(false);
	const inputRef = useRef<HTMLInputElement>(null);
	const containerRef = useRef<HTMLDivElement>(null);

	const filtered = suggestions.filter(
		(s) => s.toLowerCase().includes(input.toLowerCase()) && !tags.includes(s),
	);

	const addTag = (tag: string) => {
		const trimmed = tag.trim().toLowerCase();
		if (trimmed && !tags.includes(trimmed)) {
			onChange([...tags, trimmed]);
		}
		setInput("");
		setShowSuggestions(false);
	};

	const removeTag = (tag: string) => {
		onChange(tags.filter((t) => t !== tag));
	};

	const handleKeyDown = (e: React.KeyboardEvent) => {
		if (e.key === "Enter" || e.key === ",") {
			e.preventDefault();
			if (input.trim()) addTag(input);
		} else if (e.key === "Backspace" && !input && tags.length > 0) {
			removeTag(tags[tags.length - 1]);
		} else if (e.key === "Escape") {
			setShowSuggestions(false);
		}
	};

	useEffect(() => {
		const handleClickOutside = (e: MouseEvent) => {
			if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
				setShowSuggestions(false);
			}
		};
		document.addEventListener("mousedown", handleClickOutside);
		return () => document.removeEventListener("mousedown", handleClickOutside);
	}, []);

	return (
		<div ref={containerRef} className={cn("relative", className)}>
			<div className="flex flex-wrap items-center gap-1 bg-secondary/50 border border-border rounded px-2 py-1 min-h-[30px]">
				{tags.map((tag) => (
					<span
						key={tag}
						className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-accent/15 text-accent"
					>
						{tag}
						<button
							onClick={() => removeTag(tag)}
							className="hover:text-foreground transition-colors"
						>
							<X className="w-2.5 h-2.5" />
						</button>
					</span>
				))}
				<input
					ref={inputRef}
					type="text"
					value={input}
					onChange={(e) => {
						setInput(e.target.value);
						setShowSuggestions(true);
					}}
					onFocus={() => setShowSuggestions(true)}
					onKeyDown={handleKeyDown}
					placeholder={tags.length === 0 ? placeholder : ""}
					className="flex-1 min-w-[60px] text-xs bg-transparent text-foreground placeholder:text-muted-foreground/40 focus:outline-none"
				/>
			</div>

			{showSuggestions && input && filtered.length > 0 && (
				<div className="absolute z-10 mt-1 w-full bg-card border border-border rounded-md shadow-md max-h-32 overflow-y-auto">
					{filtered.map((tag) => (
						<button
							key={tag}
							onClick={() => addTag(tag)}
							className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-secondary/40 transition-colors"
						>
							{tag}
						</button>
					))}
				</div>
			)}
		</div>
	);
}
