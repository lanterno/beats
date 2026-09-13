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
			<p className="text-[11px] font-medium text-muted-foreground mb-1">{label}</p>
			<button
				type="button"
				onClick={handleCopy}
				className="w-full text-left text-[11.5px] font-code text-foreground bg-secondary rounded-xl px-3 py-2 overflow-x-auto cursor-pointer hover:bg-sidebar-accent transition-colors whitespace-nowrap focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				title="Click to copy"
			>
				{code}
				{copied && (
					<span className="ml-2 font-body font-bold text-foreground text-[10.5px]">copied!</span>
				)}
			</button>
		</div>
	);
}
