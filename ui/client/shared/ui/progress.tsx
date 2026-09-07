import * as ProgressPrimitive from "@radix-ui/react-progress";
import type * as React from "react";

import { cn } from "../lib";

// React 19 passes `ref` as an ordinary prop — no forwardRef needed.
function Progress({
	className,
	value,
	ref,
	...props
}: React.ComponentPropsWithRef<typeof ProgressPrimitive.Root>) {
	return (
		<ProgressPrimitive.Root
			ref={ref}
			className={cn("relative h-4 w-full overflow-hidden rounded-full bg-muted", className)}
			{...props}
		>
			<ProgressPrimitive.Indicator
				className="h-full w-full flex-1 bg-accent/85 transition-all"
				style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
			/>
		</ProgressPrimitive.Root>
	);
}

export { Progress };
