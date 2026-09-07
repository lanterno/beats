import type * as React from "react";

import { cn } from "../lib";

// React 19 passes `ref` as an ordinary prop, so none of these need forwardRef.

function Table({ className, ref, ...props }: React.ComponentPropsWithRef<"table">) {
	return (
		<div className="relative w-full overflow-auto">
			<table ref={ref} className={cn("w-full caption-bottom text-base", className)} {...props} />
		</div>
	);
}

function TableHeader({ className, ref, ...props }: React.ComponentPropsWithRef<"thead">) {
	return <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />;
}

function TableBody({ className, ref, ...props }: React.ComponentPropsWithRef<"tbody">) {
	return <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

function TableFooter({ className, ref, ...props }: React.ComponentPropsWithRef<"tfoot">) {
	return (
		<tfoot
			ref={ref}
			className={cn("border-t bg-secondary/30 font-medium last:[&>tr]:border-b-0", className)}
			{...props}
		/>
	);
}

function TableRow({ className, ref, ...props }: React.ComponentPropsWithRef<"tr">) {
	return (
		<tr
			ref={ref}
			className={cn(
				"border-b transition-colors hover:bg-secondary/50 data-[state=selected]:bg-secondary",
				className,
			)}
			{...props}
		/>
	);
}

function TableHead({ className, ref, ...props }: React.ComponentPropsWithRef<"th">) {
	return (
		<th
			ref={ref}
			className={cn(
				"h-12 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0",
				className,
			)}
			{...props}
		/>
	);
}

function TableCell({ className, ref, ...props }: React.ComponentPropsWithRef<"td">) {
	return (
		<td
			ref={ref}
			className={cn("p-4 align-middle [&:has([role=checkbox])]:pr-0", className)}
			{...props}
		/>
	);
}

function TableCaption({ className, ref, ...props }: React.ComponentPropsWithRef<"caption">) {
	return (
		<caption ref={ref} className={cn("mt-4 text-sm text-muted-foreground", className)} {...props} />
	);
}

export { Table, TableBody, TableCaption, TableCell, TableFooter, TableHead, TableHeader, TableRow };
