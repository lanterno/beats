/**
 * JoinRequestsSection — who is waiting on an invite link with an approval
 * step. Approving makes the member; declining closes the request.
 */

import { UserPlus } from "lucide-react";
import { toast } from "sonner";
import type { JoinRequest } from "@/entities/organisation";
import { useDecideJoinRequest, useJoinRequests } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { HEADING, HEADING_ICON, LEAD, LIST, ROW } from "./styles";

export function JoinRequestsSection({ organisationId }: { organisationId: string }) {
	const requests = useJoinRequests(organisationId);
	const decide = useDecideJoinRequest(organisationId);

	const answer = (request: JoinRequest, decision: "approved" | "declined") =>
		decide.mutate(
			{ requestId: request.id, decision },
			{
				onSuccess: () =>
					toast.success(
						decision === "approved"
							? `${request.name} joined`
							: `${request.name}'s request declined`,
					),
				onError: (err) => toast.error(describeError(err, "The request could not be decided.")),
			},
		);

	return (
		<section aria-label="Join requests" className="mb-8">
			<h2 className={HEADING}>
				<UserPlus className={HEADING_ICON} />
				Join requests
			</h2>
			<Panel padding="px-5 py-1">
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
								<Button
									type="button"
									size="sm"
									variant="secondary"
									disabled={decide.isPending}
									onClick={() => answer(request, "declined")}
								>
									Decline
								</Button>
								<Button
									type="button"
									size="sm"
									disabled={decide.isPending}
									onClick={() => answer(request, "approved")}
								>
									Approve
								</Button>
							</li>
						))}
					</ul>
				)}
			</Panel>
		</section>
	);
}
