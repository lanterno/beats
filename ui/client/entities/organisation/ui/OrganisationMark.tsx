/**
 * OrganisationMark — how an organisation's project is marked wherever
 * projects are listed (docs/organisations.md, stage 2): the logo if there
 * is one, else a lettered tile in the muted wash, and the name. Small by
 * default, for a row; `size="md"` for a header.
 */

import { cn } from "@/shared/lib";

export interface OrganisationMarkProps {
	name: string;
	logoUrl?: string;
	size?: "sm" | "md";
	/** Leave out the name, for a tight row where the tile alone marks it. */
	tileOnly?: boolean;
	className?: string;
}

export function OrganisationMark({
	name,
	logoUrl,
	size = "sm",
	tileOnly = false,
	className,
}: OrganisationMarkProps) {
	const tile = size === "md" ? "w-6 h-6 text-[11px] rounded-lg" : "w-4 h-4 text-[9px] rounded-md";
	const initial = name.trim().charAt(0).toUpperCase() || "?";
	return (
		<span
			className={cn(
				"inline-flex items-center gap-1.5 min-w-0 whitespace-nowrap",
				size === "md" ? "text-sm font-bold" : "text-[11px] font-bold",
				"text-muted-foreground",
				className,
			)}
			title={tileOnly ? name : undefined}
		>
			{logoUrl ? (
				<img
					src={logoUrl}
					alt=""
					className={cn(tile, "shrink-0 object-cover bg-secondary")}
					loading="lazy"
				/>
			) : (
				<span
					aria-hidden="true"
					className={cn(
						tile,
						"shrink-0 grid place-items-center bg-secondary text-foreground font-heading font-extrabold leading-none",
					)}
				>
					{initial}
				</span>
			)}
			{tileOnly ? (
				<span className="sr-only">{name}</span>
			) : (
				<span className="truncate">{name}</span>
			)}
		</span>
	);
}
