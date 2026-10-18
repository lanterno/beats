/**
 * ReportLinksSection — every report link that still opens, across clients
 * (docs/billing.md, phase 1c). A link outlives the session that made it:
 * signing out and removing a passkey leave it working. So this is where a
 * session that may have been someone else's is answered: each live link can
 * be turned off, and Turn off all report links ends every one at once.
 * Ended links, and making or replacing one, are on the Clients page.
 */

import { Link2 } from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";
import { useClients } from "@/entities/client";
import {
	ReportLinkRow,
	TURN_OFF_QUESTION,
	useDeleteReportLink,
	useReportLinks,
	useTurnOffReportLinks,
} from "@/entities/report-link";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Panel, useConfirm } from "@/shared/ui";
import { DANGER_HOVER, HEADING, HEADING_ICON, LEAD, LINKISH, LIST } from "./styles";

export function ReportLinksSection() {
	const linksQuery = useReportLinks();
	const { data: clients } = useClients();
	const { data: archivedClients } = useClients({ archived: true });
	const remove = useDeleteReportLink();
	const turnOffAll = useTurnOffReportLinks();
	const { confirm, confirmDialog } = useConfirm();

	const live = (linksQuery.data ?? []).filter((link) => link.state === "live");
	const clientNames = new Map(
		[...(clients ?? []), ...(archivedClients ?? [])].map((client) => [client.id, client.name]),
	);

	const turnOff = async (linkId: string) => {
		if (!(await confirm(TURN_OFF_QUESTION))) return;
		remove.mutate(linkId, {
			onSuccess: () => toast.success("Report link turned off"),
			onError: (err) => toast.error(describeError(err, "Failed to turn the link off")),
		});
	};

	const handleTurnOffAll = async () => {
		const sure = await confirm({
			title: "Turn off every report link?",
			detail: `All ${live.length === 1 ? "1 link" : `${live.length} links`}, for every client, stop opening at once: anyone holding one will see “This report link isn't valid”. They can't be turned back on.`,
			confirmLabel: "Turn off all",
		});
		if (!sure) return;
		turnOffAll.mutate(null, {
			onSuccess: (n) =>
				toast.success(n === 1 ? "1 report link turned off" : `${n} report links turned off`),
			onError: (err) => toast.error(describeError(err, "Failed to turn the links off")),
		});
	};

	return (
		<section className="mb-8" aria-label="Report links">
			<h2 className={HEADING}>
				<Link2 className={HEADING_ICON} />
				Report links
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>
					Links your clients open their reports with, no sign-in needed. Signing out or removing a
					passkey does not end them; turning them off does. Make and replace them on the{" "}
					<Link to="/clients" className={LINKISH}>
						Clients page
					</Link>
					.
				</p>

				{linksQuery.isError ? (
					<p className="text-[12.5px] text-muted-foreground font-medium">
						Report links aren't available right now.
					</p>
				) : !linksQuery.data ? (
					<p className={LEAD}>Loading...</p>
				) : live.length === 0 ? (
					<p className={LEAD}>No report link is working right now.</p>
				) : (
					<>
						<ul className={LIST}>
							{live.map((link) => (
								<li key={link.id} className="py-2">
									<ReportLinkRow
										link={link}
										clientName={clientNames.get(link.clientId)}
										actions={
											<button
												type="button"
												onClick={() => void turnOff(link.id)}
												disabled={remove.isPending}
												className={cn(LINKISH, "text-destructive-ink")}
											>
												Turn off
											</button>
										}
									/>
								</li>
							))}
						</ul>
						<Button
							type="button"
							variant="secondary"
							size="sm"
							className={DANGER_HOVER}
							onClick={() => void handleTurnOffAll()}
							disabled={turnOffAll.isPending}
						>
							Turn off all report links
						</Button>
					</>
				)}
			</Panel>
			{confirmDialog}
		</section>
	);
}
