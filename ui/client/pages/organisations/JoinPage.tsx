/**
 * JoinPage — `/organisations/join/:token`: what an invite opens. The
 * organisation, the role it gives, and a Join button; a link with an
 * approval step leaves a request instead and says so. The API answers one
 * 404 for a token that is unknown or addressed to another account, and
 * 410 for one that was real and has closed.
 */

import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import {
	OrganisationMark,
	ROLE_HINTS,
	ROLE_LABELS,
	useInvitePreview,
	useJoinOrganisation,
} from "@/entities/organisation";
import { ApiError, describeError } from "@/shared/api";
import { Button, Panel } from "@/shared/ui";
import { LEAD, LINKISH, TITLE } from "./styles";

function failure(err: unknown): string {
	if (err instanceof ApiError && err.statusCode === 410) return "This invite is no longer valid.";
	if (err instanceof ApiError && err.statusCode === 404) {
		return "This invite isn't for this account, or doesn't exist.";
	}
	return describeError(err, "The invite could not be read.");
}

/** "a member", "an admin" — the right article for the role's word. */
function asA(role: string): string {
	return /^[aeiou]/i.test(role) ? `an ${role}` : `a ${role}`;
}

export default function JoinPage() {
	const { token } = useParams<{ token: string }>();
	const navigate = useNavigate();
	const preview = useInvitePreview(token);
	const join = useJoinOrganisation();
	const [pending, setPending] = useState(false);

	const accept = () => {
		if (!token) return;
		join.mutate(token, {
			onSuccess: (result) => {
				if (result.status === "joined") {
					toast.success(`Joined ${result.membership.organisation.name}`);
					navigate(`/organisations/${result.membership.organisation.id}`);
				} else {
					setPending(true);
				}
			},
			onError: (err) => {
				// Asking again on a link already asked on is the answer "it is
				// still waiting", not a failure — a reload loses the local
				// pending flag, and this is how it comes back.
				if (err instanceof ApiError && err.code === "JOIN_REQUEST_PENDING") setPending(true);
				else toast.error(describeError(err, "You could not join."));
			},
		});
	};

	const invite = preview.data;
	const role = invite ? ROLE_LABELS[invite.role].toLowerCase() : "";

	return (
		<div className="max-w-xl mx-auto px-4 sm:px-6 py-10">
			{preview.error ? (
				<Panel role="alert" padding="px-6 py-[22px]">
					<p className="font-heading text-lg font-extrabold text-foreground">
						{failure(preview.error)}
					</p>
					<Link to="/organisations" className={`${LINKISH} mt-3 inline-block`}>
						Your organisations
					</Link>
				</Panel>
			) : !invite ? (
				<p className="text-sm text-muted-foreground px-2">Loading…</p>
			) : (
				<Panel padding="px-6 py-[22px]" className="space-y-4">
					<div className="flex items-center gap-3">
						<OrganisationMark
							name={invite.organisation.name}
							logoUrl={invite.organisation.logoUrl}
							size="md"
							tileOnly
						/>
						<h1 className={TITLE}>{invite.organisation.name}</h1>
					</div>
					{invite.alreadyMember ? (
						<>
							<p className="text-[13px] font-medium text-foreground">You're already a member.</p>
							<Link to={`/organisations/${invite.organisation.id}`} className={LINKISH}>
								Open {invite.organisation.name}
							</Link>
						</>
					) : pending ? (
						<>
							<p className="text-[13px] font-medium text-foreground">
								Your request is waiting for an admin. Once someone decides,{" "}
								{invite.organisation.name} appears under your organisations.
							</p>
							<Link to="/organisations" className={LINKISH}>
								Your organisations
							</Link>
						</>
					) : (
						<>
							<p className="text-[13px] font-medium text-foreground">
								{invite.addressed
									? `You've been invited to join as ${asA(role)}.`
									: invite.requiresApproval
										? `Anyone with this link may join as ${asA(role)}, after approval.`
										: `Anyone with this link may join as ${asA(role)}.`}{" "}
								<span className="text-muted-foreground">{ROLE_HINTS[invite.role]}</span>
							</p>
							<p className={LEAD}>
								Joining adds its projects to your own list once you are assigned. On those projects
								it sees your finished entries — start, end, duration and the note — your absences as
								a date and a type, and a managed contract's balance. Nothing else crosses: not your
								own projects, nothing about now, and you can always read exactly what it holds.
							</p>
							<Button type="button" size="sm" onClick={accept} disabled={join.isPending}>
								{join.isPending
									? "Joining…"
									: invite.requiresApproval && !invite.addressed
										? "Ask to join"
										: "Join"}
							</Button>
						</>
					)}
				</Panel>
			)}
		</div>
	);
}
