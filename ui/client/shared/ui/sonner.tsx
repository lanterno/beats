import type * as React from "react";
import { Toaster as Sonner } from "sonner";

type ToasterProps = React.ComponentProps<typeof Sonner>;

/*
  Sonner styles its toasts from its own stylesheet, which is not in a cascade
  layer and so outranks any Tailwind utility on the same property. Its CSS
  variables are the supported way in: a toast is a small cloud — the panel
  colour, the panel's ink, no border, and a 1rem radius.
*/
const cloud = {
	"--normal-bg": "var(--color-card)",
	"--normal-text": "var(--color-foreground)",
	"--normal-border": "transparent",
	"--border-radius": "1rem",
} as React.CSSProperties;

const Toaster = ({ style, ...props }: ToasterProps) => {
	return (
		<Sonner
			className="toaster group"
			closeButton
			style={{ ...cloud, ...style }}
			toastOptions={{
				classNames: {
					toast: "group toast",
					description: "group-[.toast]:text-muted-foreground",
					actionButton: "group-[.toast]:bg-accent group-[.toast]:text-accent-foreground",
					cancelButton: "group-[.toast]:bg-secondary group-[.toast]:text-foreground",
				},
			}}
			{...props}
		/>
	);
};

export { Toaster };
