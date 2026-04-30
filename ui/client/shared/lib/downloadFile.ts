/**
 * Trigger an authenticated file download.
 *
 * `<a href>` won't carry the JWT Bearer token the rest of the API uses,
 * so we fetch the response into a Blob, build a temporary object URL,
 * and click() a dynamic anchor. Errors surface via the toast on the
 * caller side — this helper just throws so callers can decide whether
 * to swallow / reroute.
 */
import { getSessionToken } from "@/features/auth/stores/authStore";
import { config } from "@/shared/config";

export async function downloadFile(path: string, filename: string): Promise<void> {
	const token = getSessionToken();
	const res = await fetch(`${config.apiBaseUrl}${path}`, {
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	});
	if (!res.ok) throw new Error(`Download failed (HTTP ${res.status})`);
	const blob = await res.blob();
	const a = document.createElement("a");
	a.href = URL.createObjectURL(blob);
	a.download = filename;
	a.click();
	URL.revokeObjectURL(a.href);
}
