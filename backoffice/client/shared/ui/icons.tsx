/**
 * The handful of icons the back office draws, and the app's mark. Written
 * out rather than pulled from an icon package: a privileged surface takes
 * on no dependency for a dozen shapes. All decorative; the words beside them,
 * or a button's `aria-label`, are the label.
 */

import type { ReactNode } from "react";

interface IconProps {
	className?: string;
}

function Icon({ className = "size-[18px]", children }: IconProps & { children: ReactNode }) {
	return (
		<svg
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2"
			strokeLinecap="round"
			strokeLinejoin="round"
			className={className}
			aria-hidden="true"
			focusable="false"
		>
			{children}
		</svg>
	);
}

export function BellIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<path d="M6 8a6 6 0 0 1 12 0c0 7 3 8 3 8H3s3-1 3-8" />
			<path d="M10.3 20a2 2 0 0 0 3.4 0" />
		</Icon>
	);
}

export function PersonIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<circle cx="12" cy="8" r="4" />
			<path d="M4 21a8 8 0 0 1 16 0" />
		</Icon>
	);
}

export function BuildingIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<rect x="4" y="3" width="16" height="18" rx="2" />
			<path d="M9 8h.01M15 8h.01M9 12h.01M15 12h.01M10 21v-4h4v4" />
		</Icon>
	);
}

export function ShieldIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
		</Icon>
	);
}

export function DatabaseIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<ellipse cx="12" cy="5" rx="8" ry="3" />
			<path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
			<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
		</Icon>
	);
}

export function ClipboardIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<rect x="5" y="4" width="14" height="17" rx="2" />
			<path d="M9 3h6v3H9zM9 13l2 2 4-4" />
		</Icon>
	);
}

/** Jobs and windows: work that waits out a clock. */
export function ClockIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<circle cx="12" cy="12" r="9" />
			<path d="M12 7v5l3 2" />
		</Icon>
	);
}

/** Privacy and compliance: what is promised about someone's data. */
export function LockIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<rect x="5" y="11" width="14" height="10" rx="2" />
			<path d="M8 11V7a4 4 0 0 1 8 0v4" />
		</Icon>
	);
}

/** The audit log: a page of lines, read and never edited. */
export function LinesIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<rect x="5" y="3" width="14" height="18" rx="2" />
			<path d="M9 8h6M9 12h6M9 16h3" />
		</Icon>
	);
}

export function SunIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<circle cx="12" cy="12" r="4" />
			<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
		</Icon>
	);
}

export function MoonIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<path d="M21 13a9 9 0 1 1-10-10 7 7 0 0 0 10 10z" />
		</Icon>
	);
}

export function MonitorIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<rect x="3" y="4" width="18" height="12" rx="2" />
			<path d="M8 20h8M12 16v4" />
		</Icon>
	);
}

export function CheckIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<path d="M5 12l5 5 9-10" />
		</Icon>
	);
}

export function ArrowLeftIcon(props: IconProps) {
	return (
		<Icon {...props}>
			<path d="M19 12H5M11 6l-6 6 6 6" />
		</Icon>
	);
}

/** The day ring (`shared/brand/mark.svg`), as ui/'s BrandMark draws it. */
export function BrandMark({ className }: IconProps) {
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
