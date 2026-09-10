/**
 * Settings Page
 * Appearance, data export, API info, and developer tools.
 */

import {
	Download,
	FileJson,
	FileSpreadsheet,
	Moon,
	Palette,
	Rows3,
	Sun,
	Terminal,
	Upload,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useProjects } from "@/entities/project";
import { config } from "@/shared/config";
import { COLOR_MODES, DENSITIES, downloadFile, THEMES, useTheme } from "@/shared/lib";
import { sessionToken } from "@/shared/session";
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
import { WebhooksSection } from "./WebhooksSection";

export default function Settings() {
	const { data: projects } = useProjects();
	const [importing, setImporting] = useState(false);
	const { theme, setTheme, mode, setMode, density, setDensity } = useTheme();

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
			<h1 className="font-heading text-2xl text-foreground mb-1">Settings</h1>
			<p className="text-sm text-muted-foreground mb-8">
				Appearance, data export, and developer tools.
			</p>

			{/* Appearance — Theme */}
			<section className="mb-8">
				<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
					<Palette className="w-4 h-4 text-accent" />
					Theme
				</h2>
				<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4">
					<div className="flex flex-wrap gap-2">
						{THEMES.map((t) => (
							<button
								type="button"
								key={t.id}
								onClick={() => setTheme(t.id)}
								className={`flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium border transition-colors ${
									theme === t.id
										? "border-accent bg-accent/10 text-accent"
										: "border-border bg-secondary/20 text-foreground hover:bg-secondary/40"
								}`}
							>
								<span
									className="w-3 h-3 rounded-full shrink-0"
									style={{ backgroundColor: t.accent }}
								/>
								{t.label}
							</button>
						))}
					</div>
				</div>
			</section>

			{/* Appearance — Color Mode */}
			<section className="mb-8">
				<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
					{mode === "dark" ? (
						<Moon className="w-4 h-4 text-accent" />
					) : (
						<Sun className="w-4 h-4 text-accent" />
					)}
					Color Mode
				</h2>
				<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4">
					<div className="flex flex-wrap gap-2">
						{COLOR_MODES.map((m) => (
							<button
								type="button"
								key={m.id}
								onClick={() => setMode(m.id)}
								className={`flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium border transition-colors ${
									mode === m.id
										? "border-accent bg-accent/10 text-accent"
										: "border-border bg-secondary/20 text-foreground hover:bg-secondary/40"
								}`}
							>
								{m.id === "dark" ? <Moon className="w-3 h-3" /> : <Sun className="w-3 h-3" />}
								{m.label}
							</button>
						))}
					</div>
				</div>
			</section>

			{/* Appearance — Density */}
			<section className="mb-8">
				<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
					<Rows3 className="w-4 h-4 text-accent" />
					Layout Density
				</h2>
				<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4">
					<div className="flex flex-wrap gap-2">
						{DENSITIES.map((d) => (
							<button
								type="button"
								key={d.id}
								onClick={() => setDensity(d.id)}
								className={`px-3 py-2 rounded-md text-xs font-medium border transition-colors ${
									density === d.id
										? "border-accent bg-accent/10 text-accent"
										: "border-border bg-secondary/20 text-foreground hover:bg-secondary/40"
								}`}
							>
								{d.label}
							</button>
						))}
					</div>
				</div>
			</section>

			{/* Data Export */}
			<section className="mb-8">
				<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
					<Download className="w-4 h-4 text-accent" />
					Data Export
				</h2>
				<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden divide-y divide-border/40">
					{/* CSV */}
					<div className="p-4">
						<div className="flex items-start gap-3">
							<FileSpreadsheet className="w-5 h-5 text-accent/70 mt-0.5 shrink-0" />
							<div className="flex-1">
								<p className="text-sm font-medium text-foreground">Sessions CSV</p>
								<p className="text-xs text-muted-foreground mt-0.5">
									Export sessions as a spreadsheet with date, project, start, end, duration, notes,
									and tags.
								</p>
								<div className="flex flex-wrap gap-2 mt-3">
									<button
										type="button"
										onClick={() => handleExportCSV()}
										className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
									>
										All sessions
									</button>
									{activeProjects.map((p) => (
										<button
											type="button"
											key={p.id}
											onClick={() => handleExportCSV(p.id)}
											className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/60 transition-colors"
										>
											{p.name}
										</button>
									))}
								</div>
							</div>
						</div>
					</div>

					{/* JSON */}
					<div className="p-4">
						<div className="flex items-start gap-3">
							<FileJson className="w-5 h-5 text-accent/70 mt-0.5 shrink-0" />
							<div className="flex-1">
								<p className="text-sm font-medium text-foreground">Full JSON Backup</p>
								<p className="text-xs text-muted-foreground mt-0.5">
									Complete dump of all projects and sessions. Re-importable for disaster recovery.
								</p>
								<button
									type="button"
									onClick={handleExportJSON}
									className="mt-3 px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
								>
									Download backup
								</button>
							</div>
						</div>
					</div>
				</div>
			</section>

			{/* Data Import */}
			<section className="mb-8">
				<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
					<Upload className="w-4 h-4 text-accent" />
					Data Import
				</h2>
				<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4">
					<p className="text-xs text-muted-foreground mb-3">
						Restore from a JSON backup file. Records are upserted by ID — safe to re-import without
						duplicates.
					</p>
					<label className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/60 transition-colors cursor-pointer">
						<Upload className="w-3.5 h-3.5" />
						{importing ? "Importing..." : "Choose backup file"}
						<input
							type="file"
							accept=".json"
							onChange={handleImport}
							disabled={importing}
							className="hidden"
						/>
					</label>
				</div>
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
				<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
					<Terminal className="w-4 h-4 text-accent" />
					Developer
				</h2>
				<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden divide-y divide-border/40">
					<div className="p-4">
						<p className="text-xs text-muted-foreground mb-1">API Base URL</p>
						<code className="text-sm text-foreground font-mono bg-secondary/40 px-2 py-0.5 rounded">
							{apiBase}
						</code>
					</div>
					<div className="p-4">
						<p className="text-xs text-muted-foreground mb-2">Quick Start</p>
						<div className="space-y-2">
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
				</div>
			</section>
		</div>
	);
}

/**
 * The linked `home.space` identity — the account's second door.
 *
 * Renders nothing at all unless the instance actually offers SSO, so a
 * deployment without an identity service shows the settings page it always
 * showed.
 */
