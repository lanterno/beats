import type { ApiAbsence } from "@/shared/api";
import type { Absence } from "./types";

export function toAbsence(api: ApiAbsence): Absence {
	return {
		id: api.id,
		projectId: api.project_id,
		date: api.date,
		halfDay: api.half_day ?? false,
		type: api.type,
		note: api.note ?? undefined,
	};
}
