/**
 * ArchivePage — `/organisations/:id/archive`: the person's own hours that
 * are one organisation's working-time record, by project, kept after
 * leaving (docs/organisations-roadmap.md, stage 2). Read-only, and
 * exportable as CSV; it reads through the caller's own repository, so it
 * is here whether the membership is still open or ended.
 */

import { Download } from "lucide-react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";
import { archiveCsvUrl, useArchive } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { downloadFile, formatDate, hoursText } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { EntriesTable } from "./EntriesTable";
import { LEAD, LINKISH, TITLE } from "./styles";

export default function ArchivePage() {
	const { id = "" } = useParams<{ id: string }>();
	const archive = useArchive(id);
	const data = archive.data;

	const download = async () => {
		if (!data) return;
		try {
			await downloadFile(archiveCsvUrl(id), `${data.organisation.name}-hours.csv`);
			toast.success("Downloaded your hours");
		} catch (err) {
			toast.error(describeError(err, "The download failed."));
		}
	};

	if (archive.error) {
		return (
			<div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
				<Panel role="alert" padding="px-6 py-[22px]">
					<p className="font-heading text-lg font-extrabold text-foreground">
						This archive could not be read.
					</p>
					<p className="mt-1 text-xs text-muted-foreground">
						{describeError(archive.error, "Nothing came back.")}
					</p>
					<Link to="/organisations" className={`${LINKISH} mt-3 inline-block`}>
						Your organisations
					</Link>
				</Panel>
			</div>
		);
	}
	if (!data) return <p className="text-sm text-muted-foreground px-6 py-6">Loading…</p>;

	const name = data.organisation.name;
	return (
		<div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-5 pb-24">
			<header className="flex items-center gap-3 flex-wrap">
				<h1 className={TITLE}>{data.leftAt ? `${name} (left)` : `${name} — your hours`}</h1>
				<Button
					type="button"
					variant="secondary"
					size="sm"
					className="ml-auto"
					onClick={() => void download()}
				>
					<Download aria-hidden="true" />
					Download CSV
				</Button>
			</header>
			<p className="text-sm font-medium text-foreground/90">
				Joined {formatDate(data.joinedAt)}
				{data.leftAt && `, left ${formatDate(data.leftAt)}`}. {hoursText(data.hours)} in total.
			</p>
			<p className="text-[12.5px] font-medium text-foreground/80">
				Read-only: these hours are {name}'s working-time record and your own copy of it. Nothing
				here can be changed.
			</p>

			{data.projects.length === 0 ? (
				<Panel padding="px-6 py-[22px]">
					<p className={LEAD}>No hours were shared with {name}.</p>
				</Panel>
			) : (
				data.projects.map((project) => (
					<Panel
						key={project.projectId}
						role="region"
						aria-label={project.name}
						padding="px-6 py-5"
						className="space-y-3"
					>
						<div className="flex items-center gap-2">
							<span
								className="w-2.5 h-2.5 rounded-full shrink-0"
								style={{ backgroundColor: project.color ?? "var(--color-muted-foreground)" }}
								aria-hidden="true"
							/>
							<h2 className="font-heading text-[15px] font-extrabold text-foreground">
								{project.name}
							</h2>
							<span className="ml-auto font-mono text-[13px] font-bold text-foreground">
								{hoursText(project.hours)}
							</span>
						</div>
						{project.entries.length === 0 ? (
							<p className={LEAD}>No entries.</p>
						) : (
							<EntriesTable entries={project.entries} label={`Entries on ${project.name}`} />
						)}
					</Panel>
				))
			)}
		</div>
	);
}
