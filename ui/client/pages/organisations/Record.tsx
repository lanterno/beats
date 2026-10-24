/** `/organisations/:id/record` — what the organisation sees in a month. Admins. */
import { useOrgRecord } from "@/entities/organisation";
import { RecordPage } from "./RecordPage";

export default function Record() {
	return <RecordPage variant="record" useRecord={useOrgRecord} />;
}
