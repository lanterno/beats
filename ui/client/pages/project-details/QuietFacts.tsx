/**
 * QuietFacts — the rail's last, smallest panel: "Last tracked today 11:52 ·
 * Focus today 74". What the stats tiles and the health card used to say
 * that was worth keeping (Decision 5), in one muted line.
 */

import { useFocusScores } from "@/entities/intelligence";
import type { ProjectWithDuration } from "@/entities/project";
import type { Session } from "@/entities/session";
import { parseUtcIso, toIsoDate } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { clock, shortDate } from "./dates";

interface QuietFactsProps {
	project: ProjectWithDuration;
	sessions: Session[];
	todayIso: string;
}

export function QuietFacts({ project, sessions, todayIso }: QuietFactsProps) {
	const { data: focusScores } = useFocusScores();

	const ends = sessions.map((s) => s.endTime || s.startTime).sort();
	const latest = project.lastTrackedAt ?? ends[ends.length - 1];
	let lastTracked = "never";
	if (latest) {
		const day = toIsoDate(parseUtcIso(latest));
		lastTracked =
			day === todayIso ? `today ${clock(latest)}` : `${shortDate(day)} ${clock(latest)}`;
	}

	const todayIds = new Set(
		sessions.filter((s) => toIsoDate(parseUtcIso(s.startTime)) === todayIso).map((s) => s.id),
	);
	const scores = (focusScores ?? []).filter((f) => todayIds.has(f.beat_id)).map((f) => f.score);
	const focus =
		scores.length > 0 ? Math.round(scores.reduce((sum, s) => sum + s, 0) / scores.length) : null;

	return (
		<Panel padding="px-6 py-4" className="text-xs text-muted-foreground font-medium leading-[1.7]">
			Last tracked <b className="text-foreground font-extrabold">{lastTracked}</b>
			{focus !== null && (
				<>
					{" · "}Focus today <b className="text-foreground font-extrabold">{focus}</b>
				</>
			)}
		</Panel>
	);
}
