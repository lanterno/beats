/**
 * The card every integration on this page is rendered in.
 *
 * Six sections had copied the same section/heading/card markup, so a spacing
 * or border tweak meant six edits and they had already drifted apart.
 */

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/shared/ui";

interface IntegrationSectionProps {
	icon: LucideIcon;
	title: string;
	description: ReactNode;
	connected: boolean;
	/** Rendered under the description when connected, e.g. the account id. */
	connectedDetail?: ReactNode;
	onDisconnect: () => void;
	disconnecting?: boolean;
	/** The control that starts a connection — a button, a token field, a link. */
	children: ReactNode;
}

export function IntegrationSection({
	icon: Icon,
	title,
	description,
	connected,
	connectedDetail,
	onDisconnect,
	disconnecting = false,
	children,
}: IntegrationSectionProps) {
	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Icon className="w-4 h-4 text-accent" />
				{title}
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">{description}</p>
				{connected ? (
					<div className="flex items-center gap-3">
						<span className="text-xs text-accent font-medium">
							Connected{connectedDetail ? <> ({connectedDetail})</> : null}
						</span>
						<Button
							variant="outline"
							size="sm"
							onClick={onDisconnect}
							disabled={disconnecting}
							className="text-xs hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30"
						>
							{disconnecting ? "Disconnecting…" : "Disconnect"}
						</Button>
					</div>
				) : (
					children
				)}
			</div>
		</section>
	);
}
