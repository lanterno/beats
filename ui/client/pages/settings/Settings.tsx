/**
 * Settings Page
 * Appearance, data export, API info, and developer tools.
 */

import {
	Download,
	FileJson,
	FileSpreadsheet,
	Palette,
	Rows3,
	Terminal,
	Upload,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useProjects } from "@/entities/project";
import { config } from "@/shared/config";
import { cn, DENSITIES, downloadFile, THEMES, useTheme } from "@/shared/lib";
import { sessionToken } from "@/shared/session";
import { Button, buttonVariants, Panel } from "@/shared/ui";
import { CalendarSection } from "./CalendarSection";
import { CoachUsage } from "./CoachUsage";
import { CodeBlock } from "./CodeBlock";
import { DaemonPrivacySection } from "./DaemonPrivacySection";
import { DaemonSection } from "./DaemonSection";
import { FitbitSection } from "./FitbitSection";
import { GitHubSection } from "./GitHubSection";
import { HomeIdentitySection } from "./HomeIdentitySection";
import { OuraSection } from "./OuraSection";
import { PasskeysSection } from "./PasskeysSection";
import { CHIP_BUTTON, HEADING, HEADING_ICON, LABEL, LEAD } from "./styles";
import { WebhooksSection } from "./WebhooksSection";

export default function Settings() {
	const { data: projects } = useProjects();
	const [importing, setImporting] = useState(false);
	const { theme, setTheme, density, setDensity } = useTheme();

	const apiBase = config.apiBaseUrl;

	const downloadWithToast = async (url: string, filename: string) => {
		try {
			await downloadFile(url, filename);
			toast.success(`Downloaded ${filename}`);
		} catch {
			toast.error("Export failed");
		}
	};

	const handleExportCSV = (projectId?: string) => {
		const params = projectId ? `?project_id=${projectId}` : "";
		const suffix = projectId
			? `_${(projects ?? []).find((p) => p.id === projectId)?.name ?? "project"}`
			: "";
		const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
		downloadWithToast(`/api/export/csv/sessions${params}`, `beats_sessions${suffix}_${date}.csv`);
	};

	const handleExportJSON = () => {
		const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
		downloadWithToast("/api/export/full", `beats_backup_${date}.json`);
	};

	const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		if (!file) return;
		setImporting(true);
		try {
			const formData = new FormData();
			formData.append("file", file);
			const token = sessionToken();
			const res = await fetch(`${apiBase}/api/export/import`, {
				method: "POST",
				headers: token ? { Authorization: `Bearer ${token}` } : {},
				body: formData,
			});
			if (!res.ok) throw new Error("Import failed");
			const result = await res.json();
			const { imported } = result;
			toast.success(`Imported ${imported.projects} projects, ${imported.beats} sessions`);
		} catch {
			toast.error("Import failed — check the file format");
		} finally {
			setImporting(false);
			e.target.value = "";
		}
	};

	const activeProjects = (projects ?? []).filter((p) => !p.archived);

	return (
		<div className="max-w-3xl mx-auto px-6 py-8">
			<h1 className="font-heading text-[26px] font-extrabold tracking-[-0.01em] text-foreground mb-1">
				Settings
			</h1>
			{/* On the bare sky: the muted ink is 3:1 there, ink at 90 % reads. */}
			<p className="text-sm font-medium text-foreground/90 mb-8">
				Appearance, data export, and developer tools.
			</p>

			{/* Appearance — Theme */}
			<section className="mb-8">
				<h2 className={HEADING}>
					<Palette className={HEADING_ICON} />
					Theme
				</h2>
				<Panel padding="p-5">
					<div className="flex flex-wrap gap-2">
						{THEMES.map((t) => (
							<button
								type="button"
								key={t.id}
								onClick={() => setTheme(t.id)}
								aria-pressed={theme === t.id}
								className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold transition-colors ${
									theme === t.id
										? "bg-accent text-accent-foreground"
										: "bg-secondary text-foreground hover:bg-sidebar-accent"
								}`}
							>
								<span
									className="w-3 h-3 rounded-full shrink-0"
									style={{ backgroundColor: t.sky }}
								/>
								{t.label}
							</button>
						))}
					</div>
				</Panel>
			</section>

			{/* Appearance — Density */}
			<section className="mb-8">
				<h2 className={HEADING}>
					<Rows3 className={HEADING_ICON} />
					Layout Density
				</h2>
				<Panel padding="p-5">
					<div className="flex flex-wrap gap-2">
						{DENSITIES.map((d) => (
							<button
								type="button"
								key={d.id}
								onClick={() => setDensity(d.id)}
								aria-pressed={density === d.id}
								className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-colors ${
									density === d.id
										? "bg-accent text-accent-foreground"
										: "bg-secondary text-foreground hover:bg-sidebar-accent"
								}`}
							>
								{d.label}
							</button>
						))}
					</div>
				</Panel>
			</section>

			{/* Data Export */}
			<section className="mb-8">
				<h2 className={HEADING}>
					<Download className={HEADING_ICON} />
					Data Export
				</h2>
				<Panel padding="px-5 py-1" className="divide-y divide-border">
					{/* CSV */}
					<div className="py-4">
						<div className="flex items-start gap-3">
							<FileSpreadsheet className="w-5 h-5 text-muted-foreground mt-0.5 shrink-0" />
							<div className="flex-1 min-w-0">
								<p className="text-sm font-bold text-foreground">Sessions CSV</p>
								<p className={cn(LEAD, "mt-0.5")}>
									Export sessions as a spreadsheet with date, project, start, end, duration, notes,
									and tags.
								</p>
								<div className="flex flex-wrap items-center gap-2 mt-3">
									<Button variant="secondary" size="sm" onClick={() => handleExportCSV()}>
										All sessions
									</Button>
									{activeProjects.map((p) => (
										<button
											type="button"
											key={p.id}
											onClick={() => handleExportCSV(p.id)}
											className={CHIP_BUTTON}
										>
											{p.name}
										</button>
									))}
								</div>
							</div>
						</div>
					</div>

					{/* JSON */}
					<div className="py-4">
						<div className="flex items-start gap-3">
							<FileJson className="w-5 h-5 text-muted-foreground mt-0.5 shrink-0" />
							<div className="flex-1 min-w-0">
								<p className="text-sm font-bold text-foreground">Full JSON Backup</p>
								<p className={cn(LEAD, "mt-0.5")}>
									Complete dump of all projects and sessions. Re-importable for disaster recovery.
								</p>
								<Button variant="secondary" size="sm" onClick={handleExportJSON} className="mt-3">
									Download backup
								</Button>
							</div>
						</div>
					</div>
				</Panel>
			</section>

			{/* Data Import */}
			<section className="mb-8">
				<h2 className={HEADING}>
					<Upload className={HEADING_ICON} />
					Data Import
				</h2>
				<Panel padding="p-5">
					<p className={cn(LEAD, "mb-3")}>
						Restore from a JSON backup file. Records are upserted by ID — safe to re-import without
						duplicates.
					</p>
					<label
						className={cn(buttonVariants({ variant: "secondary", size: "sm" }), "cursor-pointer")}
					>
						<Upload />
						{importing ? "Importing..." : "Choose backup file"}
						<input
							type="file"
							accept=".json"
							onChange={handleImport}
							disabled={importing}
							className="hidden"
						/>
					</label>
				</Panel>
			</section>

			{/* Integrations */}
			<CalendarSection />
			<GitHubSection />
			<FitbitSection />
			<OuraSection />

			{/* Daemon */}
			<DaemonSection />
			<DaemonPrivacySection />

			{/* Passkeys */}
			<PasskeysSection />

			{/* Linked home.space identity */}
			<HomeIdentitySection />

			{/* Webhooks */}
			<WebhooksSection />

			{/* Coach Usage */}
			<CoachUsage />

			{/* API Info */}
			<section className="mb-8">
				<h2 className={HEADING}>
					<Terminal className={HEADING_ICON} />
					Developer
				</h2>
				<Panel padding="px-5 py-1" className="divide-y divide-border">
					<div className="py-4">
						<p className={cn(LABEL, "mb-1.5")}>API Base URL</p>
						<code className="inline-block max-w-full break-all rounded-lg bg-secondary px-2.5 py-1 text-[13px] text-foreground font-code">
							{apiBase}
						</code>
					</div>
					<div className="py-4">
						<p className={cn(LABEL, "mb-2")}>Quick Start</p>
						<div className="space-y-2.5">
							<CodeBlock
								label="Start timer"
								code={`curl -X POST ${apiBase}/api/projects/YOUR_PROJECT_ID/start -H "Content-Type: application/json" -H "Authorization: Bearer YOUR_TOKEN" -d '{"time": null}'`}
							/>
							<CodeBlock
								label="Stop timer"
								code={`curl -X POST ${apiBase}/api/projects/stop -H "Content-Type: application/json" -H "Authorization: Bearer YOUR_TOKEN" -d '{"time": null}'`}
							/>
							<CodeBlock label="Get timer status" code={`curl ${apiBase}/api/timer/status`} />
							<CodeBlock
								label="Export backup"
								code={`curl ${apiBase}/api/export/full -o backup.json`}
							/>
							<CodeBlock
								label="Import backup"
								code={`curl -X POST ${apiBase}/api/export/import -F "file=@backup.json"`}
							/>
						</div>
					</div>
				</Panel>
			</section>
		</div>
	);
}
