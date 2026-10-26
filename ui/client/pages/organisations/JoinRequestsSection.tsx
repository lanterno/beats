/**
 * JoinRequestsSection — who is waiting on an invite link with an approval
 * step, each wearing the role approving would grant (the invite's), so an
 * admin never makes someone an admin without being told. Approving makes
 * the member; declining closes the request, after a confirm — the person
 * cannot ask again on the same link while a declined request stands.
 */

import { UserPlus } from "lucide-react";
import { toast } from "sonner";
import type { JoinRequest } from "@/entities/organisation";
import { ROLE_LABELS, useDecideJoinRequest, useJoinRequests } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Button, Chip, useConfirm } from "@/shared/ui";
import { Section } from "./Section";
import { LEAD, LIST, ROW } from "./styles";

export function JoinRequestsSection({ organisationId }: { organisationId: string }) {
	const requests = useJoinRequests(organisationId);
	const decide = useDecideJoinRequest(organisationId);
	const { confirm, confirmDialog } = useConfirm();

	const answer = (request: JoinRequest, decision: "approved" | "declined") =>
		decide.mutate(
			{ requestId: request.id, decision },
			{
				onSuccess: () =>
					toast.success(
						decision === "approved"
							? `${request.name} joined as ${ROLE_LABELS[request.role].toLowerCase()}`
							: `${request.name}'s request declined`,
					),
				onError: (err) => toast.error(describeError(err, "The request could not be decided.")),
			},
		);

	const decline = async (request: JoinRequest) => {
		const ok = await confirm({
			title: `Decline ${request.name}?`,
			detail: `${request.email} asked to join. Declining closes the request; they would need a new invite to ask again.`,
			confirmLabel: "Decline",
			tone: "danger",
		});
		if (ok) answer(request, "declined");
	};

	const deciding = (request: JoinRequest) =>
		decide.isPending && decide.variables?.requestId === request.id;

	return (
		<Section label="Join requests" icon={UserPlus}>
			{requests.error ? (
				<p className={`${LEAD} py-3`} role="alert">
					{describeError(requests.error, "The requests could not be read.")}
				</p>
			) : !requests.data ? (
				<p className={`${LEAD} py-3`}>Loading…</p>
			) : requests.data.length === 0 ? (
				<p className={`${LEAD} py-3`}>Nobody is waiting.</p>
			) : (
				<ul className={LIST}>
					{requests.data.map((request) => (
						<li key={request.id} className={ROW}>
							<div className="min-w-0 flex-1">
								<p className="font-bold text-foreground truncate">{request.name}</p>
								<p className="text-muted-foreground truncate">
									{request.email} · asked {formatDate(request.requestedAt)}
								</p>
							</div>
							<Chip tone={request.role === "member" ? "wait" : "warn"}>
								{ROLE_LABELS[request.role]}
							</Chip>
							<Button
								type="button"
								size="sm"
								variant="secondary"
								disabled={deciding(request)}
								onClick={() => void decline(request)}
								aria-label={`Decline ${request.name}`}
							>
								Decline
							</Button>
							<Button
								type="button"
								size="sm"
								disabled={deciding(request)}
								onClick={() => answer(request, "approved")}
								aria-label={`Approve ${request.name} as ${ROLE_LABELS[request.role].toLowerCase()}`}
							>
								Approve
							</Button>
						</li>
					))}
				</ul>
			)}
			{confirmDialog}
		</Section>
	);
}
