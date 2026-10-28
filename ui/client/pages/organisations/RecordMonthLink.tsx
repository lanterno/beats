/**
 * RecordMonthLink — a month in the record, as a link: the decider's
 * evidence. `useOpenMonth` reads `?month=YYYY-MM` on the record page.
 */

import { Link } from "react-router";
import { LINKISH } from "./styles";

export function RecordMonthLink({
	organisationId,
	month,
	children,
}: {
	organisationId: string;
	/** A sheet month ("2026-09-01") or a bare month ("2026-09"). */
	month: string;
	children: React.ReactNode;
}) {
	return (
		<Link
			to={`/organisations/${organisationId}/record?month=${month.slice(0, 7)}`}
			className={LINKISH}
		>
			{children}
		</Link>
	);
}
