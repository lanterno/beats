/**
 * The card every integration on this page is rendered in.
 *
 * Six sections had copied the same section/heading/card markup, so a spacing
 * or border tweak meant six edits and they had already drifted apart.
 */

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button, Panel } from "@/shared/ui";
import { CHIP, CONNECTED_DOT, DANGER_HOVER, HEADING, HEADING_ICON, LEAD } from "./styles";

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
			<h2 className={HEADING}>
				<Icon className={HEADING_ICON} />
				{title}
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>{description}</p>
				{connected ? (
					<div className="flex flex-wrap items-center gap-3">
						<span className={CHIP}>
							<span className={CONNECTED_DOT} />
							Connected{connectedDetail ? <> ({connectedDetail})</> : null}
						</span>
						<Button
							variant="secondary"
							size="sm"
							onClick={onDisconnect}
							disabled={disconnecting}
							className={DANGER_HOVER}
						>
							{disconnecting ? "Disconnecting…" : "Disconnect"}
						</Button>
					</div>
				) : (
					children
				)}
			</Panel>
		</section>
	);
}
