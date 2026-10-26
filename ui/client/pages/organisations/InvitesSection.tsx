/**
 * InvitesSection — the open invites: to one address, or with no address a
 * link anyone may use until it expires, with or without an approval step.
 * The API sends no email; the token is returned once, here, and the
 * inviter passes the link on — so a new invite ends in its URL with a Copy
 * button, and every row has one.
 */

import { Copy, Mail, Plus, X } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Invite, InviteInput, OrgRole } from "@/entities/organisation";
import {
	inviteUrl,
	ROLE_HINTS,
	ROLE_LABELS,
	useCreateInvite,
	useInvites,
	useRevokeInvite,
} from "@/entities/organisation";
import { apiFieldErrors, describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Button, Dialog, useConfirm } from "@/shared/ui";
import { QueryBody, Section } from "./Section";
import { ERROR, FIELD, LABEL, LINKISH, LIST, REMOVE, ROW } from "./styles";

/** The roles an invite gives — every one but owner, which is given by an
 * owner to a member, never by invite (403 OWNER_ROLE_RESERVED). */
const INVITE_ROLES: OrgRole[] = ["member", "viewer", "manager", "admin"];

async function copyLink(token: string) {
	try {
		await navigator.clipboard.writeText(inviteUrl(token));
		toast.success("Invite link copied");
	} catch {
		toast.error("The link could not be copied.");
	}
}

function NewInviteDialog({
	organisationId,
	onClose,
}: {
	organisationId: string;
	onClose: () => void;
}) {
	const id = useId();
	const create = useCreateInvite(organisationId);
	const [email, setEmail] = useState("");
	const [role, setRole] = useState<OrgRole>("member");
	const [requiresApproval, setRequiresApproval] = useState(false);
	const [days, setDays] = useState("14");
	const [errors, setErrors] = useState<Record<string, string>>({});
	const [created, setCreated] = useState<Invite | null>(null);

	const save = async () => {
		const expiresInDays = Number(days);
		if (!Number.isInteger(expiresInDays) || expiresInDays < 1 || expiresInDays > 90) {
			setErrors({ expires_in_days: "Between 1 and 90 days." });
			return;
		}
		setErrors({});
		const input: InviteInput = {
			email: email.trim() || undefined,
			role,
			requiresApproval: email.trim() ? false : requiresApproval,
			expiresInDays,
		};
		try {
			const invite = await create.mutateAsync(input);
			setCreated(invite);
		} catch (err) {
			// Only email and expires_in_days render under their fields; an
			// error on anything else folds into the general line rather than
			// being set under a key nothing shows.
			const fields = apiFieldErrors(err);
			const shown: Record<string, string> = {};
			const stray: string[] = [];
			for (const [key, message] of Object.entries(fields)) {
				if (key === "email" || key === "expires_in_days") shown[key] = message;
				else stray.push(message);
			}
			if (stray.length > 0 || Object.keys(shown).length === 0) {
				shown.general = stray.join(" ") || describeError(err, "The invite could not be made.");
			}
			setErrors(shown);
		}
	};

	if (created) {
		const url = inviteUrl(created.token);
		return (
			<Dialog
				open
				onClose={onClose}
				title="Invite made"
				description={
					created.email
						? `Send this link to ${created.email}; only that account can take it.`
						: "Anyone with this link may use it until it expires."
				}
				contentClassName="sm:w-full sm:max-w-[460px]"
			>
				<div className="space-y-3">
					<div>
						<label htmlFor={`${id}-url`} className={LABEL}>
							Invite link
						</label>
						<input
							id={`${id}-url`}
							type="text"
							readOnly
							value={url}
							className={`${FIELD} font-code text-xs`}
						/>
					</div>
					<div className="flex justify-end gap-2.5">
						<Button type="button" variant="secondary" size="sm" onClick={onClose}>
							Done
						</Button>
						<Button type="button" size="sm" onClick={() => void copyLink(created.token)}>
							<Copy aria-hidden="true" />
							Copy link
						</Button>
					</div>
				</div>
			</Dialog>
		);
	}

	return (
		<Dialog
			open
			onClose={onClose}
			title="New invite"
			description="To one address, or with no address a link anyone may use."
			contentClassName="sm:w-full sm:max-w-[460px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void save();
				}}
				noValidate
				className="space-y-3"
			>
				<div>
					<label htmlFor={`${id}-email`} className={LABEL}>
						Email
					</label>
					<input
						id={`${id}-email`}
						type="email"
						value={email}
						onChange={(e) => setEmail(e.target.value)}
						placeholder="Optional · leave empty for a link"
						maxLength={254}
						autoFocus
						aria-invalid={errors.email ? true : undefined}
						aria-describedby={errors.email ? `${id}-email-error` : undefined}
						className={FIELD}
					/>
					{errors.email && (
						<p id={`${id}-email-error`} className={ERROR}>
							{errors.email}
						</p>
					)}
				</div>
				<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
					<div>
						<label htmlFor={`${id}-role`} className={LABEL}>
							Role
						</label>
						<select
							id={`${id}-role`}
							value={role}
							onChange={(e) => setRole(e.target.value as OrgRole)}
							aria-describedby={`${id}-role-hint`}
							className={FIELD}
						>
							{INVITE_ROLES.map((r) => (
								<option key={r} value={r}>
									{ROLE_LABELS[r]}
								</option>
							))}
						</select>
						<p id={`${id}-role-hint`} className="mt-1 text-xs text-muted-foreground">
							{ROLE_HINTS[role]}
						</p>
					</div>
					<div>
						<label htmlFor={`${id}-days`} className={LABEL}>
							Expires in days
						</label>
						<input
							id={`${id}-days`}
							type="number"
							min={1}
							max={90}
							value={days}
							onChange={(e) => setDays(e.target.value)}
							aria-invalid={errors.expires_in_days ? true : undefined}
							aria-describedby={errors.expires_in_days ? `${id}-days-error` : undefined}
							className={FIELD}
						/>
						{errors.expires_in_days && (
							<p id={`${id}-days-error`} className={ERROR}>
								{errors.expires_in_days}
							</p>
						)}
					</div>
				</div>
				<label
					className={`flex items-center gap-2 text-[13px] font-medium ${
						email.trim() ? "text-muted-foreground" : "text-foreground"
					}`}
				>
					<input
						type="checkbox"
						checked={!email.trim() && requiresApproval}
						onChange={(e) => setRequiresApproval(e.target.checked)}
						disabled={Boolean(email.trim())}
						className="accent-accent"
					/>
					{email.trim()
						? "An addressed invite needs no approval: only that account can take it."
						: "Needs approval — whoever opens the link asks to join, and an admin decides"}
				</label>
				{errors.general && (
					<p role="alert" className={ERROR}>
						{errors.general}
					</p>
				)}
				<div className="flex justify-end gap-2.5 pt-1">
					<Button
						type="button"
						variant="secondary"
						size="sm"
						onClick={onClose}
						disabled={create.isPending}
					>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={create.isPending}>
						{create.isPending ? "Making…" : "Make invite"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}

export function InvitesSection({ organisationId }: { organisationId: string }) {
	const invites = useInvites(organisationId);
	const revoke = useRevokeInvite(organisationId);
	const [creating, setCreating] = useState(false);
	const { confirm, confirmDialog } = useConfirm();

	const revokeInvite = async (invite: Invite) => {
		const ok = await confirm({
			title: `Revoke this invite${invite.email ? ` to ${invite.email}` : " link"}?`,
			detail: "It stops working at once; anyone holding it can no longer join.",
			confirmLabel: "Revoke",
			tone: "danger",
		});
		if (!ok) return;
		revoke.mutate(invite.id, {
			onSuccess: () => toast.success("Invite revoked"),
			onError: (err) => toast.error(describeError(err, "The invite could not be revoked.")),
		});
	};

	return (
		<Section
			label="Invites"
			icon={Mail}
			action={
				<button type="button" onClick={() => setCreating(true)} className={LINKISH}>
					<Plus className="w-3 h-3 inline-block mr-1" aria-hidden="true" />
					New invite
				</button>
			}
		>
			<QueryBody
				query={invites}
				errorText="The invites could not be read."
				empty="No open invites."
			>
				{(rows) => (
					<ul className={LIST}>
						{rows.map((invite) => (
							<li key={invite.id} className={ROW}>
								<div className="min-w-0 flex-1">
									<p className="font-bold text-foreground truncate">{invite.email ?? "Link"}</p>
									<p className="text-muted-foreground truncate">
										{ROLE_LABELS[invite.role]}
										{invite.requiresApproval && " · needs approval"} · expires{" "}
										{formatDate(invite.expiresAt)}
									</p>
								</div>
								<button
									type="button"
									onClick={() => void copyLink(invite.token)}
									className={LINKISH}
								>
									Copy link
								</button>
								<button
									type="button"
									onClick={() => revokeInvite(invite)}
									disabled={revoke.isPending}
									aria-label={`Revoke the invite ${invite.email ? `to ${invite.email}` : "link"}`}
									className={REMOVE}
								>
									<X className="w-3.5 h-3.5" aria-hidden="true" />
								</button>
							</li>
						))}
					</ul>
				)}
			</QueryBody>
			{creating && (
				<NewInviteDialog organisationId={organisationId} onClose={() => setCreating(false)} />
			)}
			{confirmDialog}
		</Section>
	);
}
