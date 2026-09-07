import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "../lib";

const buttonVariants = cva(
	"inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-base font-medium ring-offset-background transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
	{
		variants: {
			variant: {
				default: "bg-primary text-primary-foreground hover:bg-primary/90",
				destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
				outline:
					"border border-input bg-transparent hover:bg-secondary hover:text-secondary-foreground",
				secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
				ghost: "hover:bg-secondary hover:text-secondary-foreground",
				link: "text-accent underline-offset-4 hover:underline",
			},
			size: {
				default: "h-10 px-4 py-2",
				sm: "h-9 rounded-md px-3",
				lg: "h-11 rounded-md px-8",
				icon: "h-10 w-10",
			},
		},
		defaultVariants: {
			variant: "default",
			size: "default",
		},
	},
);

export interface ButtonProps
	extends React.ComponentPropsWithRef<"button">,
		VariantProps<typeof buttonVariants> {
	asChild?: boolean;
}

// React 19 passes `ref` as an ordinary prop — no forwardRef needed.
function Button({ className, variant, size, asChild = false, type, ref, ...props }: ButtonProps) {
	const Comp = asChild ? Slot : "button";
	return (
		<Comp
			// A <button> with no type submits the form it sits in. Actions are
			// the common case here, so default to "button" and let a real submit
			// say so; `asChild` renders someone else's element, which has no type.
			type={asChild ? undefined : (type ?? "button")}
			className={cn(buttonVariants({ variant, size, className }))}
			ref={ref}
			{...props}
		/>
	);
}

export { Button, buttonVariants };
