/**
 * ArchivedClientLinks — the report links of an archived client with no
 * panel in the month shown. The month report lists an archived client only
 * when it has entries that month, and its links keep working after the
 * archive (docs/billing.md, phase 1c), so without this they would be on the
 * Clients page for no month at all: a live one only in Settings, where it
 * can be turned off but not previewed or replaced, and an ended one nowhere.
 */

import { useState } from "react";
import type { ReportLink } from "@/entities/report-link";
import { ReportLinkDialog, ReportLinkPreviewDialog } from "./ReportLinkDialog";
import { ReportLinksSection } from "./ReportLinksSection";

type Sharing = { mode: "replace"; link: ReportLink } | { mode: "preview"; link: ReportLink };

export interface ArchivedClientLinksProps {
	clientId: string;
	clientName: string;
	links: readonly ReportLink[];
	/** The client's billed projects, by name: what a replacing link may cover. */
	shareable: readonly { id: string; name: string }[];
	projectNames: ReadonlyMap<string, string>;
}

export function ArchivedClientLinks({
	clientId,
	clientName,
	links,
	shareable,
	projectNames,
}: ArchivedClientLinksProps) {
	const [sharing, setSharing] = useState<Sharing | null>(null);
	return (
		<>
			<ReportLinksSection
				clientName={clientName}
				links={links}
				billedProjectIds={shareable.map((project) => project.id)}
				projectNames={projectNames}
				onPreview={(link) => setSharing({ mode: "preview", link })}
				onReplace={(link) => setSharing({ mode: "replace", link })}
			/>
			{sharing?.mode === "preview" ? (
				<ReportLinkPreviewDialog
					link={sharing.link}
					clientName={clientName}
					onClose={() => setSharing(null)}
				/>
			) : (
				sharing && (
					<ReportLinkDialog
						key={sharing.link.id}
						clientId={clientId}
						clientName={clientName}
						billedProjects={shareable}
						replacing={sharing.link}
						onClose={() => setSharing(null)}
					/>
				)
			)}
		</>
	);
}
