/**
 * The control plane's HTTP client. Same-origin only: the operator app serves
 * this UI itself, so there is no base URL and no bearer token — the
 * credential is IAP's cookie, which the browser attaches on its own. Writes
 * carry the browser's own Origin header, which the server checks; nothing
 * here can or should add one.
 */

export class OperatorApiError extends Error {
	constructor(
		public readonly statusCode: number,
		message: string,
		public readonly code?: string,
	) {
		super(message);
		this.name = "OperatorApiError";
	}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, {
		...init,
		headers: { Accept: "application/json", ...init?.headers },
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new OperatorApiError(
			response.status,
			body.detail || `Request failed: ${response.statusText}`,
			body.code,
		);
	}
	return response.json();
}

export function get<T>(path: string): Promise<T> {
	return request<T>(path);
}

export function post<T>(path: string, body: unknown): Promise<T> {
	return request<T>(path, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
}
