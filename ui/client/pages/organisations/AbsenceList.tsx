/**
 * AbsenceList — the absences an organisation holds: the date, the kind as
 * a word on its tint (the app's idiom for vacation, sick, holiday, other —
 * never a raw API string), and whether it was a half day. The record page
 * and the archive draw the same list from the same `RecordAbsence`.
 */

import { ABSENCE_TYPE_LABELS } from "@/entities/absence";
import type { RecordAbsence } from "@/entities/organisation";
import { cn, formatDateOnly } from "@/shared/lib";
import { LABEL, TINT, TINT_PILL } from "./styles";

export function AbsenceList({ absences, label }: { absences: RecordAbsence[]; label: string }) {
	if (absences.length === 0) return null;
	return (
		<div>
			<p id={`${label}-label`} className={LABEL}>
				Absences
			</p>
			<ul aria-label={label} className="text-[12.5px] text-foreground space-y-1">
				{absences.map((absence) => (
					<li key={`${absence.date}-${absence.type}`} className="flex items-center gap-2">
						<span className="font-medium">{formatDateOnly(absence.date)}</span>
						<span className={cn(TINT_PILL, TINT[absence.type as keyof typeof TINT] ?? TINT.other)}>
							{(
								ABSENCE_TYPE_LABELS[absence.type as keyof typeof ABSENCE_TYPE_LABELS] ??
								absence.type
							).toLowerCase()}
						</span>
						{absence.halfDay && <span className="text-muted-foreground">half day</span>}
					</li>
				))}
			</ul>
		</div>
	);
}
