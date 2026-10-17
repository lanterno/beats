/**
 * Whether the nav offers Clients: once there is someone to bill or work to
 * bill — a client, archived or not, or a freelance project. Before that the
 * page would only say "add a client", and most people never bill anyone.
 */

import { useClients } from "@/entities/client";
import type { ProjectWithDuration } from "@/entities/project";

export function useShowClients(projects: ProjectWithDuration[]): boolean {
	const freelance = projects.some((project) => project.kind === "freelance");
	const { data: active } = useClients();
	const { data: archived } = useClients({ archived: true });
	return freelance || (active?.length ?? 0) > 0 || (archived?.length ?? 0) > 0;
}
