/**
 * `/organisations/:id/record` — what the organisation sees in a month. Record
 * readers: owners, admins and viewers, and managers narrowed to their teams.
 */
import { useOrgRecord } from "@/entities/organisation";
import { RecordPage } from "./RecordPage";

export default function Record() {
	return <RecordPage variant="record" useRecord={useOrgRecord} />;
}
