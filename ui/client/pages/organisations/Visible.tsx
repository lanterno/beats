/** `/organisations/:id/visible` — what the organisation sees of the caller. Everyone. */
import { useVisible } from "@/entities/organisation";
import { RecordPage } from "./RecordPage";

export default function Visible() {
	return <RecordPage variant="visible" useRecord={useVisible} />;
}
