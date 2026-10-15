/**
 * The app's mark, the day ring (`shared/brand/mark.svg`): a faint ring, a gold
 * arc from twelve round two thirds of the dial, and the sun where it ends, on a
 * navy tile in either hour. Decorative: the name beside it is the label.
 */
export function BrandMark({ className }: { className?: string }) {
	return (
		<svg viewBox="0 0 120 120" className={className} aria-hidden="true" focusable="false">
			<rect width="120" height="120" rx="27" fill="#1A2446" />
			<circle cx="60" cy="60" r="34" fill="none" stroke="#2E3E6E" strokeWidth="8" />
			<path
				d="M60 26A34 34 0 1 1 30.56 77"
				fill="none"
				stroke="#F5C35E"
				strokeWidth="8"
				strokeLinecap="round"
			/>
			<circle cx="30.56" cy="77" r="9" fill="#F5C35E" />
		</svg>
	);
}
