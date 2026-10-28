/**
 * ClosingSection — the owner's end of #347, under Settings. Closing is
 * notice, not a lock: tracking carries on, every member sees the banner,
 * and deletion only unlocks once the notice has run out — the API refuses
 * it earlier, and the button says why rather than letting a click explain.
 * The section talks about the two exports because they are the point of
 * the notice: the organisation's record dies with it (the owner's last
 * record.csv/compliance.csv is the employer's legal copy), while a
 * member's hours never do — each project comes back to them as their own.
 */

import { CalendarOff } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import type { Organisation } from "@/entities/organisation";
import { useBeginClosing, useCancelClosing, useDeleteOrganisation } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, Dialog, useConfirm } from "@/shared/ui";
import { Section } from "./Section";
import { DANGER_HOVER, FIELD, LABEL, LEAD, LINKISH } from "./styles";

/** The API's default notice, mirrored for the date input's initial value. */
const DEFAULT_NOTICE_DAYS = 60;

function plusDays(days: number): string {
	const d = new Date();
	d.setDate(d.getDate() + days);
	return d.toISOString().slice(0, 10);
}

export function ClosingSection({ organisation }: { organisation: Organisation }) {
	const navigate = useNavigate();
	const begin = useBeginClosing(organisation.id);
	const cancel = useCancelClosing(organisation.id);
	const remove = useDeleteOrganisation(organisation.id);
	const { confirm, confirmDialog } = useConfirm();
	const [asking, setAsking] = useState(false);
	const [closesOn, setClosesOn] = useState(() => plusDays(DEFAULT_NOTICE_DAYS));
	const [error, setError] = useState<string | null>(null);
	const id = useId();

	const closing = organisation.closesOn;
	const due = closing !== undefined && closing <= new Date().toISOString().slice(0, 10);

	const startNow = () => {
		setError(null);
		begin.mutate(closesOn, {
			onSuccess: () => {
				toast.success(`${organisation.name} closes on ${closesOn}`);
				setAsking(false);
			},
			onError: (err) => setError(describeError(err, "The closing could not be started.")),
		});
	};

	const deleteNow = async () => {
		const ok = await confirm({
			title: `Delete ${organisation.name}?`,
			detail:
				"Its working-time record is destroyed with it — the record and compliance CSVs you downloaded are the copy that remains. Every member keeps their own hours: each project comes back to them as a personal one.",
			confirmLabel: "Delete",
		});
		if (!ok) return;
		remove.mutate(undefined, {
			onSuccess: () => {
				toast.success(`${organisation.name} was deleted; members keep their own hours`);
				navigate("/organisations");
			},
			onError: (err) => toast.error(describeError(err, "The organisation could not be deleted.")),
		});
	};

	return (
		<Section label="Closing" icon={CalendarOff} bodyClassName="p-5 space-y-2.5">
			{closing ? (
				<>
					<p className="text-[13px] leading-normal font-medium text-foreground">
						{organisation.name} closes on <span className="font-mono">{closing}</span>. Every member
						sees this and can take their archive; download the record and compliance CSVs for every
						month the law makes you keep before the day — they are the copy that survives.
					</p>
					<div className="flex gap-2.5">
						<Button
							type="button"
							variant="secondary"
							size="sm"
							onClick={() =>
								cancel.mutate(undefined, {
									onSuccess: () => toast.success("The closing was called off"),
									onError: (err) =>
										toast.error(describeError(err, "The closing could not be cancelled.")),
								})
							}
							disabled={cancel.isPending || remove.isPending}
						>
							Cancel closing
						</Button>
						<Button
							type="button"
							variant="secondary"
							size="sm"
							className={DANGER_HOVER}
							onClick={() => void deleteNow()}
							disabled={!due || remove.isPending}
							title={due ? undefined : `Deletion unlocks on ${closing}`}
						>
							{remove.isPending ? "Deleting…" : due ? "Delete now" : `Unlocks ${closing}`}
						</Button>
					</div>
				</>
			) : (
				<>
					<p className={LEAD}>
						Closing gives every member notice in-app — at least 30 days — before the organisation
						and its working-time record are deleted. Members keep their own hours either way: each
						project comes back to them as a personal one.
					</p>
					<button type="button" onClick={() => setAsking(true)} className={LINKISH}>
						Close {organisation.name}…
					</button>
				</>
			)}

			{asking && (
				<Dialog
					open
					onClose={() => !begin.isPending && setAsking(false)}
					title={`Close ${organisation.name}…`}
					description="The day it closes, shown to every member from now until then."
					contentClassName="sm:w-full sm:max-w-[420px]"
				>
					<div className="space-y-3">
						<div>
							<label htmlFor={`${id}-closes-on`} className={LABEL}>
								Closes on
							</label>
							<input
								id={`${id}-closes-on`}
								type="date"
								value={closesOn}
								min={plusDays(30)}
								onChange={(e) => setClosesOn(e.target.value)}
								className={FIELD}
							/>
						</div>
						<p className={LEAD}>
							Tracking carries on until then. Deletion stays locked until the day, and the closing
							can be called off at any time before it.
						</p>
						{error && (
							<p className="text-sm text-destructive-ink" role="alert">
								{error}
							</p>
						)}
						<div className="flex justify-end gap-2.5 pt-1">
							<Button
								type="button"
								variant="secondary"
								size="sm"
								onClick={() => setAsking(false)}
								disabled={begin.isPending}
							>
								Cancel
							</Button>
							<Button type="button" size="sm" onClick={startNow} disabled={begin.isPending}>
								{begin.isPending ? "Starting…" : "Start the notice"}
							</Button>
						</div>
					</div>
				</Dialog>
			)}
			{confirmDialog}
		</Section>
	);
}
