/**
 * ArchivePage — `/organisations/:id/archive`: the person's own hours that
 * are one organisation's working-time record, by project, kept after
 * leaving (docs/organisations-roadmap.md, stage 2). Read-only, and
 * exportable as CSV; it reads through the caller's own repository, so it
 * is here whether the membership is still open or ended.
 */

import { Archive, Download } from "lucide-react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";
import { archiveCsvUrl, useArchive } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { cn, downloadFile, formatDate, hoursText } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { AbsenceList } from "./AbsenceList";
import { EntriesTable } from "./EntriesTable";
import { CRUMB, LEAD, LINKISH, PAGE, PAGE_TITLE, PAGEBAR } from "./styles";

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
			<div className={PAGE}>
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
	if (!data) {
		return (
			<div className={PAGE}>
				<Panel padding="px-5 py-3" className={PAGEBAR}>
					<p className={LEAD}>Loading…</p>
				</Panel>
			</div>
		);
	}

	const name = data.organisation.name;
	return (
		<div className={PAGE}>
			<Panel padding="px-5 py-3" className={PAGEBAR}>
				<Archive className="w-5 h-5 text-muted-foreground shrink-0" aria-hidden="true" />
				<div className="min-w-0">
					{data.leftAt ? (
						<Link to="/organisations" className={CRUMB}>
							Organisations
						</Link>
					) : (
						<Link to={`/organisations/${id}`} className={CRUMB}>
							{name}
						</Link>
					)}
					<h1 className={cn(PAGE_TITLE, "truncate")}>
						{data.leftAt ? `${name} (left)` : `${name} — your hours`}
					</h1>
				</div>
				<span className="font-mono text-[13px] font-bold text-foreground whitespace-nowrap">
					{hoursText(data.hours)}
					<span className="font-body font-medium text-muted-foreground"> in total</span>
				</span>
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
			</Panel>
			<Panel padding="px-5 py-3" className="space-y-1">
				<p className="text-[13px] font-medium text-foreground">
					Joined {formatDate(data.joinedAt)}
					{data.leftAt && `, left ${formatDate(data.leftAt)}`}.
				</p>
				<p className={LEAD}>
					{data.leftAt ? (
						<>
							These hours are {name}'s working-time record of your membership; this is your own read
							of them, and {name} cannot change what it was given.
						</>
					) : (
						<>
							These hours are {name}'s working-time record — and still your own entries: editing or
							deleting one on your timeline changes what {name} holds, except inside a month it has
							approved.
						</>
					)}
				</p>
			</Panel>

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
						<AbsenceList absences={project.absences} label={`Absences on ${project.name}`} />
					</Panel>
				))
			)}
		</div>
	);
}
