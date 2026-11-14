/**
 * The control plane's HTTP client. Same-origin only: the operator app serves
 * this UI itself, so there is no base URL and no bearer token — the
 * credential is IAP's cookie, which the browser attaches on its own. Writes
 * carry the browser's own Origin header, which the server checks; nothing
 * here can or should add one.
 */

/** One entry of the envelope's `fields` (api/src/beats/api/errors.py): the
 * argument it is about, dot-joined (empty for the arguments as a whole),
 * the validator's own sentence, and pydantic's kind of failure. */
export interface FieldProblem {
	path: string;
	message: string;
	type: string;
}

export class OperatorApiError extends Error {
	constructor(
		public readonly statusCode: number,
		message: string,
		public readonly code?: string,
		/** Only on a 422: what was wrong with each argument. */
		public readonly fields: FieldProblem[] = [],
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
			Array.isArray(body.fields) ? body.fields : [],
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
