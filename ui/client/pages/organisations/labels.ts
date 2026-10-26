/**
 * The words a row is read by. An approval row carries its own project and
 * member names (`project_name`, `member_name`), because a decider is shown
 * the row but may not list the organisation's projects, and a member who
 * left is no longer in `/members`. These are the fallbacks for the one case
 * the API cannot name: an account erased to a tombstone, whose membership
 * keeps the record but not the person (docs/organisations.md, decision 3).
 */

export function memberLabel(name: string | undefined): string {
	return name ?? "A former member";
}

export function projectLabel(name: string | undefined): string {
	return name ?? "a project";
}
