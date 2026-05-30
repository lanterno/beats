/**
 * Projects index page — `/projects`. Gives projects a home: a sortable,
 * searchable table on desktop and a card list on mobile, backed by the
 * P3.0 aggregation endpoint so it loads in one round-trip regardless of
 * project count.
 *
 * Per the roadmap (P3.1):
 * - Columns: color+name, category, integrations icons, weekly progress,
 *   last tracked.
 * - Sortable column headers; search via the shared selector.
 * - Mobile breakpoint switches to a card list with the same data.
 * - Zero-state with the New Project CTA when there are no visible projects.
 */
import { GitBranch, Layers, Plus, Search, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
	filterAndRankProjects,
	NewProjectDialog,
	type Project,
	type ProjectWithDuration,
	useProjects,
	visibleProjects,
} from "@/entities/project";
import { cn, formatDuration } from "@/shared/lib";
import { Button } from "@/shared/ui";

type SortKey = "name" | "category" | "weekly" | "lastTracked";

interface SortState {
	key: SortKey;
	direction: "asc" | "desc";
}

const SORT_DEFAULTS: Record<SortKey, "asc" | "desc"> = {
	name: "asc",
	category: "asc",
	weekly: "desc",
	lastTracked: "desc",
};

function compareByKey(a: ProjectWithDuration, b: ProjectWithDuration, key: SortKey): number {
	switch (key) {
		case "name":
			return a.name.localeCompare(b.name);
		case "category":
			return (a.category ?? "").localeCompare(b.category ?? "");
		case "weekly":
			return a.weeklyMinutes - b.weeklyMinutes;
		case "lastTracked": {
			const aT = a.lastTrackedAt ? Date.parse(a.lastTrackedAt) : 0;
			const bT = b.lastTrackedAt ? Date.parse(b.lastTrackedAt) : 0;
			return aT - bT;
		}
	}
}

function applySort(list: ProjectWithDuration[], sort: SortState): ProjectWithDuration[] {
	const copy = [...list];
	copy.sort((a, b) => {
		const base = compareByKey(a, b, sort.key);
		return sort.direction === "asc" ? base : -base;
	});
	return copy;
}

function formatRelativeDays(iso: string | undefined): string {
	if (!iso) return "—";
	const ts = Date.parse(iso);
	if (Number.isNaN(ts)) return "—";
	const days = Math.floor((Date.now() - ts) / (24 * 60 * 60 * 1000));
	if (days <= 0) return "Today";
	if (days === 1) return "1 day ago";
	if (days < 30) return `${days} days ago`;
	const months = Math.floor(days / 30);
	if (months === 1) return "1 month ago";
	return `${months} months ago`;
}

interface FilteredListProps {
	projects: ProjectWithDuration[];
	query: string;
	sort: SortState;
}

function deriveDisplayList({ projects, query, sort }: FilteredListProps): ProjectWithDuration[] {
	const filtered = filterAndRankProjects(projects, query) as ProjectWithDuration[];
	return applySort(filtered, sort);
}

export default function ProjectsIndex() {
	const navigate = useNavigate();
	const { data: projects, isLoading } = useProjects();
	const [query, setQuery] = useState("");
	const [sort, setSort] = useState<SortState>({ key: "weekly", direction: "desc" });
	const [dialogOpen, setDialogOpen] = useState(false);

	const list = useMemo(
		() => deriveDisplayList({ projects: visibleProjects(projects), query, sort }),
		[projects, query, sort],
	);
	const visibleCount = useMemo(() => visibleProjects(projects).length, [projects]);

	const handleSort = (key: SortKey) => {
		setSort((current) =>
			current.key === key
				? { key, direction: current.direction === "asc" ? "desc" : "asc" }
				: { key, direction: SORT_DEFAULTS[key] },
		);
	};

	return (
		<div className="max-w-6xl mx-auto px-6 py-6 space-y-5">
			<header className="flex items-center gap-3">
				<Layers className="w-5 h-5 text-accent" />
				<h1 className="font-heading text-xl text-foreground">Projects</h1>
				<span className="text-xs text-muted-foreground">{visibleCount} active</span>
				<Button type="button" size="sm" className="ml-auto" onClick={() => setDialogOpen(true)}>
					<Plus className="w-3.5 h-3.5" />
					New project
				</Button>
			</header>

			<div className="relative max-w-md">
				<Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/60 pointer-events-none" />
				<input
					type="search"
					placeholder="Search projects…"
					value={query}
					onChange={(e) => setQuery(e.target.value)}
					aria-label="Search projects"
					className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
				/>
			</div>

			{isLoading ? (
				<p className="text-sm text-muted-foreground">Loading projects…</p>
			) : list.length === 0 ? (
				<EmptyState hasAnyVisibleProjects={visibleCount > 0} onCreate={() => setDialogOpen(true)} />
			) : (
				<>
					<ProjectsTable
						list={list}
						sort={sort}
						onSort={handleSort}
						onNavigate={(id) => navigate(`/project/${id}`)}
					/>
					<ProjectsCardList list={list} />
				</>
			)}

			<NewProjectDialog
				open={dialogOpen}
				onClose={() => setDialogOpen(false)}
				onCreated={(project) => navigate(`/project/${project.id}`)}
			/>
		</div>
	);
}

function EmptyState({
	hasAnyVisibleProjects,
	onCreate,
}: {
	hasAnyVisibleProjects: boolean;
	onCreate: () => void;
}) {
	return (
		<div className="rounded-lg border border-dashed border-border/80 bg-card/40 p-10 text-center">
			<Layers className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
			{hasAnyVisibleProjects ? (
				<p className="text-sm text-muted-foreground">No projects match your search.</p>
			) : (
				<>
					<p className="text-sm text-foreground mb-1">No projects yet</p>
					<p className="text-xs text-muted-foreground mb-4">
						Create your first project to start tracking time.
					</p>
					<Button type="button" onClick={onCreate}>
						<Plus className="w-3.5 h-3.5" />
						New project
					</Button>
				</>
			)}
		</div>
	);
}

interface ProjectsTableProps {
	list: ProjectWithDuration[];
	sort: SortState;
	onSort: (key: SortKey) => void;
	onNavigate: (projectId: string) => void;
}

function ProjectsTable({ list, sort, onSort, onNavigate }: ProjectsTableProps) {
	return (
		<div className="hidden md:block overflow-x-auto rounded-lg border border-border/80 bg-card shadow-soft">
			<table className="w-full text-sm">
				<thead className="bg-secondary/30 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
					<tr>
						<SortHeader label="Project" sortKey="name" current={sort} onSort={onSort} />
						<SortHeader label="Category" sortKey="category" current={sort} onSort={onSort} />
						<th className="text-left px-3 py-2">Integrations</th>
						<SortHeader
							label="This week"
							sortKey="weekly"
							current={sort}
							onSort={onSort}
							align="right"
						/>
						<SortHeader
							label="Last tracked"
							sortKey="lastTracked"
							current={sort}
							onSort={onSort}
							align="right"
						/>
					</tr>
				</thead>
				<tbody>
					{list.map((project) => (
						<tr
							key={project.id}
							className="border-t border-border/40 hover:bg-secondary/20 cursor-pointer"
							onClick={() => onNavigate(project.id)}
						>
							<td className="px-3 py-2">
								<div className="flex items-center gap-2 min-w-0">
									<span
										className="inline-block w-2 h-2 rounded-full shrink-0"
										style={{ backgroundColor: project.color }}
										aria-hidden="true"
									/>
									<Link
										to={`/project/${project.id}`}
										onClick={(e) => e.stopPropagation()}
										className="text-foreground font-medium truncate hover:text-accent"
									>
										{project.name}
									</Link>
									{project.description && (
										<span className="text-xs text-muted-foreground/60 truncate hidden lg:inline">
											· {project.description}
										</span>
									)}
								</div>
							</td>
							<td className="px-3 py-2 text-muted-foreground">
								{project.category ?? <span className="text-muted-foreground/40">—</span>}
							</td>
							<td className="px-3 py-2">
								<IntegrationIcons project={project} />
							</td>
							<td className="px-3 py-2 text-right">
								<WeeklyProgress project={project} />
							</td>
							<td className="px-3 py-2 text-right text-muted-foreground tabular-nums">
								{formatRelativeDays(project.lastTrackedAt)}
							</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}

function SortHeader({
	label,
	sortKey,
	current,
	onSort,
	align = "left",
}: {
	label: string;
	sortKey: SortKey;
	current: SortState;
	onSort: (key: SortKey) => void;
	align?: "left" | "right";
}) {
	const isActive = current.key === sortKey;
	return (
		<th
			scope="col"
			className={cn("px-3 py-2", align === "right" ? "text-right" : "text-left")}
			aria-sort={isActive ? (current.direction === "asc" ? "ascending" : "descending") : "none"}
		>
			<button
				type="button"
				onClick={() => onSort(sortKey)}
				className={cn(
					"inline-flex items-center gap-1 uppercase tracking-[0.14em] text-[10px] transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded",
					isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
				)}
			>
				{label}
				{isActive && <span aria-hidden="true">{current.direction === "asc" ? "↑" : "↓"}</span>}
			</button>
		</th>
	);
}

function ProjectsCardList({ list }: { list: ProjectWithDuration[] }) {
	return (
		<div className="md:hidden space-y-2">
			{list.map((project) => (
				<Link
					key={project.id}
					to={`/project/${project.id}`}
					className="block rounded-lg border border-border/80 bg-card p-3 hover:bg-secondary/20 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
				>
					<div className="flex items-center gap-2 mb-1">
						<span
							className="inline-block w-2 h-2 rounded-full shrink-0"
							style={{ backgroundColor: project.color }}
							aria-hidden="true"
						/>
						<span className="text-sm font-medium text-foreground truncate flex-1">
							{project.name}
						</span>
						<IntegrationIcons project={project} />
					</div>
					{project.description && (
						<p className="text-[11px] text-muted-foreground/70 line-clamp-1 mb-1">
							{project.description}
						</p>
					)}
					<div className="flex items-center justify-between text-[11px] text-muted-foreground">
						<WeeklyProgress project={project} />
						<span className="tabular-nums">{formatRelativeDays(project.lastTrackedAt)}</span>
					</div>
				</Link>
			))}
		</div>
	);
}

function WeeklyProgress({ project }: { project: ProjectWithDuration }) {
	const goal = project.effectiveGoalOverridden
		? (project.effectiveGoal ?? null)
		: (project.effectiveGoal ?? project.weeklyGoal ?? null);
	if (project.weeklyMinutes === 0 && goal == null) {
		return <span className="text-muted-foreground/40">—</span>;
	}
	const actualHours = project.weeklyMinutes / 60;
	if (goal == null) {
		return (
			<span className="text-foreground tabular-nums">{formatDuration(project.weeklyMinutes)}</span>
		);
	}
	const pct = Math.min(100, Math.round((actualHours / goal) * 100));
	return (
		<span
			className="tabular-nums text-foreground"
			title={`${actualHours.toFixed(1)}h of ${goal}h (${pct}%)`}
		>
			{actualHours.toFixed(1)}/{goal}h
		</span>
	);
}

function IntegrationIcons({ project }: { project: Project }) {
	const hasGithub = Boolean(project.githubRepo);
	const hasAutostart = project.autostartRepos.length > 0;
	if (!hasGithub && !hasAutostart) {
		return <span className="text-muted-foreground/30">—</span>;
	}
	return (
		<div className="inline-flex items-center gap-1.5">
			{hasGithub && (
				<GitBranch
					className="w-3.5 h-3.5 text-muted-foreground"
					aria-label={`GitHub repo: ${project.githubRepo}`}
				/>
			)}
			{hasAutostart && (
				<Zap
					className="w-3.5 h-3.5 text-muted-foreground"
					aria-label={`Autostart: ${project.autostartRepos.length} path(s)`}
				/>
			)}
		</div>
	);
}
