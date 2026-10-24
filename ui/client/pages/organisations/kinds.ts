/**
 * What a project's kind is called, as the project page spells it
 * (`ProjectHeader`): the organisation pages name the kind beside each of
 * the organisation's projects.
 */
import type { ProjectKind } from "@/entities/project";

export const KIND_LABELS: Record<ProjectKind, string> = {
	day_job: "Day job",
	freelance: "Freelance",
	side_project: "Side project",
};

export const KINDS: ProjectKind[] = ["day_job", "freelance", "side_project"];
