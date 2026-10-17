/**
 * Trigger an authenticated file download.
 *
 * `<a href>` won't carry the JWT Bearer token the rest of the API uses,
 * so we fetch the response into a Blob, build a temporary object URL,
 * and click() a dynamic anchor. A refusal throws the API's own error
 * (`apiErrorFrom`), so a caller's toast can say why — and an expired
 * session signs out, as on every other call. The caller names the file:
 * a cross-origin response's Content-Disposition is not readable here.
 */
import { apiErrorFrom } from "@/shared/api";
import { config } from "@/shared/config";
import { sessionToken } from "@/shared/session";

export async function downloadFile(path: string, filename: string): Promise<void> {
	const token = sessionToken();
	const res = await fetch(`${config.apiBaseUrl}${path}`, {
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	});
	if (!res.ok) throw await apiErrorFrom(res);
	const blob = await res.blob();
	const a = document.createElement("a");
	a.href = URL.createObjectURL(blob);
	a.download = filename;
	a.click();
	URL.revokeObjectURL(a.href);
}
