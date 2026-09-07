import { useState } from "react";

/** A copyable one-line snippet. Used by the API and daemon sections. */
export function CodeBlock({ label, code }: { label: string; code: string }) {
	const [copied, setCopied] = useState(false);
	const handleCopy = () => {
		navigator.clipboard.writeText(code);
		setCopied(true);
		setTimeout(() => setCopied(false), 1500);
	};
	return (
		<div>
			<p className="text-[10px] text-muted-foreground/60 mb-0.5">{label}</p>
			<button
				type="button"
				onClick={handleCopy}
				className="w-full text-left text-[11px] font-mono text-foreground/80 bg-secondary/40 rounded px-2.5 py-1.5 overflow-x-auto cursor-pointer hover:bg-secondary/60 transition-colors whitespace-nowrap"
				title="Click to copy"
			>
				{code}
				{copied && <span className="ml-2 text-accent text-[10px]">copied!</span>}
			</button>
		</div>
	);
}
