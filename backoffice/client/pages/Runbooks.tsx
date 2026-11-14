/**
 * The runbooks (shared/runbooks.ts): the list, and one at a time. Static
 * text in the bundle; a stale one says so rather than disappearing, because
 * steps nobody re-checked are still better than none in the middle of a bad
 * night.
 */

import { Link, useParams } from "react-router";
import { isStale, RUNBOOKS, runbook, STALE_AFTER_MONTHS } from "@/shared/runbooks";
import { Chip, Empty, Page, Panel, Prose } from "@/shared/ui";

function Reviewed({ on }: { on: string }) {
	return isStale(on, new Date()) ? (
		<Chip tone="owed">Stale, reviewed {on}</Chip>
	) : (
		<Chip>Reviewed {on}</Chip>
	);
}

export function Runbooks() {
	return (
		<Page
			title="Runbooks"
			lead={`What to do when something lands. Each says when it was last reviewed, and is marked stale after ${STALE_AFTER_MONTHS} months.`}
		>
			<Panel raised>
				<ul className="px-6 py-2">
					{RUNBOOKS.map((r) => (
						<li
							key={r.id}
							className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-hairline py-3 first:border-0"
						>
							<Link to={`/runbooks/${r.id}`} className="link min-w-[14rem] flex-1 text-[15px]">
								{r.title}
							</Link>
							<Reviewed on={r.reviewed_on} />
						</li>
					))}
				</ul>
			</Panel>
		</Page>
	);
}

export function RunbookPage() {
	const { id = "" } = useParams();
	const r = runbook(id);
	if (!r) {
		return (
			<Panel>
				<Empty title="No runbook by that name.">
					<Link to="/runbooks" className="link">
						See them all
					</Link>
				</Empty>
			</Panel>
		);
	}
	return (
		<Page title={r.title} lead={r.about} aside={<Reviewed on={r.reviewed_on} />}>
			<Panel raised title="What to do">
				<ol className="list-decimal px-6 pb-5 pl-11 text-[15px] leading-relaxed">
					{r.steps.map((step) => (
						<li key={step} className="py-1">
							{step}
						</li>
					))}
				</ol>
			</Panel>
			<Prose>
				<Link to="/runbooks" className="link">
					Every runbook
				</Link>
			</Prose>
		</Page>
	);
}
