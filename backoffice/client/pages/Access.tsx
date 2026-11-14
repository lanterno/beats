/**
 * Access and controls (docs/backoffice.md § Controls): who can reach this
 * back office, what each role may do, and the switches that change how the
 * whole product behaves — each thrown from its own review page, through the
 * runner, and recorded in the audit like every other act.
 *
 * The access review the mock drew as a checklist is here as a list to read
 * down: nothing records that you did it, by the "not decided" list in
 * docs/backoffice.md, and a box that stored nothing would only pretend.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AccessEntry, ControlState } from "@/shared/api/schema";
import { CONTROLS, type ControlName, isLimit, LIMITS, PAUSES } from "@/shared/commands";
import { minuteOf } from "@/shared/lib/format";
import {
	buttonClass,
	Chip,
	Facts,
	Failed,
	Loading,
	Page,
	Pair,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";

/** Who, if anyone, can sign in: the page's first sentence. */
export function accessHeadline(entries: AccessEntry[]): string {
	const operators = entries.filter((e) => e.role === "operator").length;
	if (entries.length === 0) return "Nobody is on the allowlist.";
	if (entries.length === 1) return "One person can reach this.";
	return `${entries.length} people can reach this, ${operators === 1 ? "one of them an operator" : `${operators} of them operators`}.`;
}

/** What a control's row says about its state. */
export function controlState(name: string, control: ControlState | undefined): string {
	if (!control?.in_force) return isLimit(name) ? "No limit" : "Running";
	if (name === "signups" && control.value) {
		return `Slowed to ${control.value} an hour, until ${minuteOf(control.until)}`;
	}
	if (isLimit(name)) return `${control.value} ${CONTROLS[name as ControlName].unit ?? ""}`.trim();
	return `Paused until ${minuteOf(control.until)}`;
}

function ControlRows({
	names,
	controls,
}: {
	names: readonly ControlName[];
	controls: ControlState[];
}) {
	return (
		<ul className="px-6 pb-3">
			{names.map((name) => {
				const control = controls.find((c) => c.name === name);
				const inForce = Boolean(control?.in_force);
				const limit = isLimit(name);
				return (
					<li
						key={name}
						className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline py-3 first:border-0"
					>
						<div className="min-w-[14rem] flex-1">
							<p className="text-[15px] font-bold">{CONTROLS[name].title}</p>
							<p className="text-[13px] text-ink-muted">{CONTROLS[name].note}</p>
							{control && inForce ? (
								<p className="mt-1 text-[13px] text-ink-muted">
									Set {minuteOf(control.set_at)} UTC by {control.set_by ?? "—"}
									{control.reason ? ` — ${control.reason}` : ""}
								</p>
							) : null}
						</div>
						<Chip tone={inForce ? (limit ? "quiet" : "owed") : "good"}>
							{controlState(name, control)}
						</Chip>
						<Link to={`/review/control.set/${name}`} className={buttonClass("secondary")}>
							{inForce ? "Change" : limit ? "Set a limit" : "Pause"}
						</Link>
						{control ? (
							<Link to={`/review/control.clear/${name}`} className={buttonClass("secondary")}>
								Clear
							</Link>
						) : null}
					</li>
				);
			})}
		</ul>
	);
}

export function Access() {
	const access = useQuery({
		queryKey: ["access"],
		queryFn: () => get<AccessEntry[]>("/api/operator/access"),
	});
	const controls = useQuery({
		queryKey: ["controls"],
		queryFn: () => get<ControlState[]>("/api/operator/controls"),
	});
	if (access.error) return <Failed error={access.error} onRetry={() => access.refetch()} />;
	if (!access.data) return <Loading />;

	return (
		<Page
			title={accessHeadline(access.data)}
			lead="Who can get in, what they can do, and the switches that change how the whole product behaves."
		>
			<Panel
				raised
				title="Switches that affect everyone"
				note="Each lands on every instance within 30 seconds and is recorded in the audit. A pause ends by itself, within 7 days at most. Use them when something is on fire."
			>
				{controls.error ? (
					<Failed bare error={controls.error} onRetry={() => controls.refetch()} />
				) : controls.data ? (
					<ControlRows names={PAUSES} controls={controls.data} />
				) : (
					<Loading />
				)}
			</Panel>
			<Panel
				title="Limits per account, for everyone"
				note="Beneath an account's own override and above the deployment's setting. These stay until cleared. Check the request log before setting one: the app retries a refusal, and a limit a real client reaches is a storm."
			>
				{controls.data ? <ControlRows names={LIMITS} controls={controls.data} /> : null}
			</Panel>
			<Pair>
				<Panel
					title="Who can get in"
					note="Read off the allowlist this deployment was started with. Changing it is a deploy."
				>
					<Table
						head={["Person", "Role"]}
						rows={access.data.map((e) => [
							e.email,
							<Chip key="r">{e.role === "operator" ? "Operator" : "Viewer"}</Chip>,
						])}
						empty={<Prose>Nobody.</Prose>}
					/>
					<Prose>
						The privacy text names one operator. It has to name anyone else before they are added.
					</Prose>
				</Panel>
				<Panel title="What each role can do">
					<Table
						head={["Can they", "Viewer", "Operator"]}
						rows={[
							["Read every page", "Yes", "Yes"],
							["Review a command", "No", "Yes"],
							["Run a command", "No", "Yes"],
							["Throw a switch", "No", "Yes"],
						]}
						empty={null}
					/>
				</Panel>
			</Pair>
			<Pair>
				<Panel title="How the door works">
					<Facts
						items={[
							["Sign-in", "Google, in front of the whole site"],
							["Allowed by", "Google account id, on the list above"],
							["Deployment", "Separate from the product"],
							["Can sign in as a user", "No, it holds no session key"],
							["Second approver", "None. One operator acts alone, and the audit is the check"],
						]}
					/>
				</Panel>
				<Panel title="Access review">
					<Prose>
						A list to read down, once a quarter. Nothing here remembers that you did it: ticking a
						box would store nothing.
					</Prose>
					<ul className="list-disc px-6 pb-5 pl-11 text-[14px]">
						<li>Everyone listed still needs access.</li>
						<li>The audit since the last review holds nothing unexplained.</li>
						<li>The privacy text still names the right people.</li>
					</ul>
				</Panel>
			</Pair>
		</Page>
	);
}
