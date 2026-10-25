/**
 * The id a client's panel carries and the overview row jumps to. One place,
 * so the row's href and the panel's id cannot drift apart.
 */
export function clientSectionId(clientId: string): string {
	return `client-${clientId}`;
}
