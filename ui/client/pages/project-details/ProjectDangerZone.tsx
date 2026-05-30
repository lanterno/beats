/**
 * Danger Zone for ProjectDetails — archive / unarchive controls.
 *
 * Archive is permanent in lieu of delete: sessions are preserved (so the
 * project's data isn't lost) but the project disappears from active
 * pickers and lists. P0.2 of the project-management revamp.
 */

import { Archive, ArchiveRestore, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useArchiveProject, useUnarchiveProject } from "@/entities/project";
import { describeError } from "@/shared/api";
import { Button } from "@/shared/ui";

interface ProjectDangerZoneProps {
	projectId: string;
	projectName: string;
	archived: boolean;
}

export function ProjectDangerZone({ projectId, projectName, archived }: ProjectDangerZoneProps) {
	const navigate = useNavigate();
	const archive = useArchiveProject();
	const unarchive = useUnarchiveProject();
	const [confirming, setConfirming] = useState(false);

	// Reset the confirm state if the project's archive status flips out
	// from under us (e.g. another tab unarchives during a confirm). `archived`
	// is the intentional trigger; the body only calls a stable setter, so
	// Biome's useExhaustiveDependencies can't see why it's there.
	// biome-ignore lint/correctness/useExhaustiveDependencies: archived is the reset trigger, not a body dependency
	useEffect(() => {
		setConfirming(false);
	}, [archived]);

	const handleArchive = () => {
		archive.mutate(projectId, {
			onSuccess: () => {
				toast.success("Project archived");
				setConfirming(false);
				// Drop the user back to the dashboard — the project they were
				// looking at has just left every active picker.
				navigate("/app");
			},
			onError: (err) => toast.error(describeError(err, "Failed to archive project")),
		});
	};

	const handleUnarchive = () => {
		unarchive.mutate(projectId, {
			onSuccess: () => toast.success("Project restored"),
			onError: (err) => toast.error(describeError(err, "Failed to restore project")),
		});
	};

	return (
		<section
			aria-labelledby="danger-zone-title"
			className="mt-10 rounded-lg border border-destructive/30 bg-destructive/5 p-4"
		>
			<header className="flex items-center gap-2 mb-1">
				<TriangleAlert className="w-4 h-4 text-destructive shrink-0" />
				<h2 id="danger-zone-title" className="text-sm font-semibold text-foreground">
					Danger zone
				</h2>
			</header>

			{archived ? (
				<>
					<p className="text-xs text-muted-foreground/80 mb-3">
						This project is archived. Restoring it makes it visible again in pickers, the sidebar,
						and lists. Sessions and history were preserved.
					</p>
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={handleUnarchive}
						disabled={unarchive.isPending}
					>
						{unarchive.isPending ? (
							<Loader2 className="w-3.5 h-3.5 animate-spin" />
						) : (
							<ArchiveRestore className="w-3.5 h-3.5" />
						)}
						Restore project
					</Button>
				</>
			) : (
				<>
					<p className="text-xs text-muted-foreground/80 mb-3">
						Archiving hides {projectName} from pickers, lists, and the sidebar. Sessions are
						preserved and you can restore the project later — there is no hard-delete by design.
					</p>
					{confirming ? (
						<div className="flex flex-wrap items-center gap-2">
							<span className="text-xs text-foreground">
								Archive <strong>{projectName}</strong>?
							</span>
							<Button
								type="button"
								variant="destructive"
								size="sm"
								onClick={handleArchive}
								disabled={archive.isPending}
							>
								{archive.isPending ? "Archiving…" : "Archive project"}
							</Button>
							<Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(false)}>
								Cancel
							</Button>
						</div>
					) : (
						<Button type="button" variant="outline" size="sm" onClick={() => setConfirming(true)}>
							<Archive className="w-3.5 h-3.5" />
							Archive project
						</Button>
					)}
				</>
			)}
		</section>
	);
}
