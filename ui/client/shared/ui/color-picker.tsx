/**
 * ColorPicker — small swatch grid with optional hex input.
 * Used for project color customization.
 * The swatches mirror PROJECT_COLORS (entities/project/model/colors.ts);
 * shared/ cannot import entities/, so the list is repeated here.
 */
import { useEffect, useRef, useState } from "react";

const SWATCHES = [
	"#4E93E3", // Blue
	"#48B48C", // Jade
	"#D98B5F", // Terracotta
	"#DE6C78", // Rose
	"#9A7BDD", // Violet
	"#C97BC4", // Orchid
	"#46B3C7", // Teal
	"#7A8CA0", // Slate
	"#6E7FCF", // Indigo
	"#8FB04A", // Olive
];

interface ColorPickerProps {
	value: string;
	onChange: (color: string) => void;
	onClose: () => void;
}

export function ColorPicker({ value, onChange, onClose }: ColorPickerProps) {
	const [hex, setHex] = useState(value);
	const ref = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const handler = (e: MouseEvent) => {
			if (ref.current && !ref.current.contains(e.target as Node)) onClose();
		};
		document.addEventListener("mousedown", handler);
		return () => document.removeEventListener("mousedown", handler);
	}, [onClose]);

	const commit = (color: string) => {
		onChange(color);
		onClose();
	};

	return (
		<div
			ref={ref}
			className="absolute z-50 top-full mt-1 left-0 rounded-2xl bg-popover shadow-card p-2.5 w-44"
			style={{ animation: "fadeSlideIn 100ms ease-out both" }}
		>
			<div className="grid grid-cols-5 gap-1.5 mb-2">
				{SWATCHES.map((c) => (
					<button
						type="button"
						key={c}
						onClick={() => commit(c)}
						className={`w-6 h-6 rounded-full border-2 transition-transform hover:scale-110 ${
							value === c ? "border-foreground" : "border-transparent"
						}`}
						style={{ backgroundColor: c }}
					/>
				))}
			</div>
			<div className="flex gap-1">
				<input
					type="text"
					value={hex}
					onChange={(e) => setHex(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === "Enter" && /^#[0-9a-fA-F]{6}$/.test(hex)) commit(hex);
					}}
					placeholder="#hex"
					className="flex-1 min-w-0 text-xs font-mono bg-secondary rounded-full px-2.5 py-1 text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
					maxLength={7}
				/>
				<button
					type="button"
					onClick={() => {
						if (/^#[0-9a-fA-F]{6}$/.test(hex)) commit(hex);
					}}
					className="px-2.5 py-1 text-[10px] font-bold rounded-full bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
				>
					Set
				</button>
			</div>
		</div>
	);
}
