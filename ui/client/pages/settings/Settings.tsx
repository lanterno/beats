/**
 * Settings Page
 * Appearance, data export, API info, and developer tools.
 */

import {
	Download,
	ExternalLink,
	FileJson,
	FileSpreadsheet,
	Fingerprint,
	Palette,
	Plus,
	Rows3,
	Terminal,
	Trash2,
	Upload,
	Webhook,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useProjects } from "@/entities/project";
import type { CredentialInfo } from "@/features/auth";
import { del, get, post } from "@/shared/api";
import { config } from "@/shared/config";
import { DENSITIES, THEMES, useTheme } from "@/shared/lib";

export default function Settings() {
	const { data: projects } = useProjects();
	const [importing, setImporting] = useState(false);
	const { theme, setTheme, density, setDensity } = useTheme();

	const apiBase = config.apiBaseUrl;

	const downloadFile = async (url: string, filename: string) => {
		try {
			const res = await fetch(`${apiBase}${url}`);
			if (!res.ok) throw new Error("Export failed");
			const blob = await res.blob();
			const a = document.createElement("a");
			a.href = URL.createObjectURL(blob);
			a.download = filename;
			a.click();
			URL.revokeObjectURL(a.href);
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
		downloadFile(`/api/export/csv/sessions${params}`, `beats_sessions${suffix}_${date}.csv`);
	};

	const handleExportJSON = () => {
		const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
		downloadFile("/api/export/full", `beats_backup_${date}.json`);
	};

	const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		if (!file) return;
		setImporting(true);
		try {
			const formData = new FormData();
			formData.append("file", file);
			const res = await fetch(`${apiBase}/api/export/import`, {
				method: "POST",
				body: formData,
			});
			if (!res.ok) throw new Error("Import failed");
			const result = await res.json();
			const { imported } = result;
			toast.success(
				`Imported ${imported.projects} projects, ${imported.beats} sessions, ${imported.intentions} intentions, ${imported.daily_notes} notes`,
			);
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
										onClick={() => handleExportCSV()}
										className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
									>
										All sessions
									</button>
									{activeProjects.map((p) => (
										<button
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
									Complete dump of all projects, sessions, intentions, and daily notes.
									Re-importable for disaster recovery.
								</p>
								<button
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

			{/* Passkeys */}
			<PasskeysSection />

			{/* Webhooks */}
			<WebhooksSection />

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
								label="Toggle timer"
								code={`curl -X POST ${apiBase}/api/timer/toggle -H "Content-Type: application/json" -d '{"project_id": "YOUR_PROJECT_ID"}'`}
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
					<div className="p-4">
						<a
							href={`${apiBase}/docs`}
							target="_blank"
							rel="noopener noreferrer"
							className="inline-flex items-center gap-1.5 text-xs text-accent hover:text-accent/80 transition-colors"
						>
							<ExternalLink className="w-3.5 h-3.5" />
							Open API docs (Swagger)
						</a>
					</div>
				</div>
			</section>
		</div>
	);
}

function PasskeysSection() {
	const [credentials, setCredentials] = useState<CredentialInfo[]>([]);
	const [loadError, setLoadError] = useState(false);
	const [deleting, setDeleting] = useState<string | null>(null);

	const loadCredentials = useCallback(async () => {
		try {
			setLoadError(false);
			const { listCredentials } = await import("@/features/auth");
			setCredentials(await listCredentials());
		} catch {
			setLoadError(true);
		}
	}, []);

	useEffect(() => {
		loadCredentials();
	}, [loadCredentials]);

	const handleDelete = async (id: string) => {
		setDeleting(id);
		try {
			const { deleteCredential } = await import("@/features/auth");
			await deleteCredential(id);
			await loadCredentials();
			toast.success("Passkey removed");
		} catch (err) {
			toast.error(err instanceof Error ? err.message : "Failed to remove passkey");
		} finally {
			setDeleting(null);
		}
	};

	const formatDate = (iso: string) => {
		try {
			return new Date(iso).toLocaleDateString(undefined, {
				year: "numeric",
				month: "short",
				day: "numeric",
			});
		} catch {
			return iso;
		}
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Fingerprint className="w-4 h-4 text-accent" />
				Passkeys
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Passkeys let you sign in securely without a password. You must keep at least one
					registered.
				</p>

				{credentials.length === 0 && !loadError && (
					<p className="text-xs text-muted-foreground/60 italic">Loading...</p>
				)}

				{loadError && (
					<div className="flex items-center gap-2">
						<p className="text-xs text-destructive">Failed to load passkeys.</p>
						<button
							onClick={loadCredentials}
							className="text-xs text-accent hover:text-accent/80 transition-colors"
						>
							Retry
						</button>
					</div>
				)}

				{credentials.length > 0 && (
					<div className="space-y-1.5">
						{credentials.map((cred) => (
							<div
								key={cred.id}
								className="flex items-center gap-2 bg-secondary/30 rounded px-2.5 py-1.5"
							>
								<Fingerprint className="w-3.5 h-3.5 text-accent/60 shrink-0" />
								<span className="text-xs text-foreground font-medium truncate flex-1">
									{cred.device_name || "Unnamed passkey"}
								</span>
								<span className="text-[10px] text-muted-foreground shrink-0">
									{formatDate(cred.created_at)}
								</span>
								{credentials.length > 1 && (
									<button
										onClick={() => handleDelete(cred.id)}
										disabled={deleting === cred.id}
										className="p-1 text-muted-foreground/40 hover:text-destructive transition-colors shrink-0 disabled:opacity-40"
										title="Remove passkey"
									>
										<Trash2 className="w-3 h-3" />
									</button>
								)}
							</div>
						))}
					</div>
				)}
			</div>
		</section>
	);
}

interface WebhookEntry {
	id: string;
	url: string;
	events: string[];
	active: boolean;
}

function WebhooksSection() {
	const [webhooks, setWebhooks] = useState<WebhookEntry[]>([]);
	const [newUrl, setNewUrl] = useState("");
	const [adding, setAdding] = useState(false);

	const loadWebhooks = useCallback(async () => {
		try {
			const data = await get<WebhookEntry[]>("/api/webhooks/");
			setWebhooks(data);
		} catch {
			// ignore if endpoint not available
		}
	}, []);

	useEffect(() => {
		loadWebhooks();
	}, [loadWebhooks]);

	const handleAdd = async () => {
		if (!newUrl.trim()) return;
		setAdding(true);
		try {
			await post("/api/webhooks/", { url: newUrl.trim() });
			setNewUrl("");
			await loadWebhooks();
			toast.success("Webhook added");
		} catch {
			toast.error("Failed to add webhook");
		} finally {
			setAdding(false);
		}
	};

	const handleDelete = async (id: string) => {
		try {
			await del(`/api/webhooks/${id}`);
			await loadWebhooks();
			toast("Webhook removed");
		} catch {
			toast.error("Failed to remove webhook");
		}
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Webhook className="w-4 h-4 text-accent" />
				Webhooks
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Receive POST requests on <code className="text-foreground/80">timer.start</code> and{" "}
					<code className="text-foreground/80">timer.stop</code> events. Works with IFTTT, Zapier,
					Home Assistant, or custom endpoints.
				</p>

				{webhooks.length > 0 && (
					<div className="space-y-1.5">
						{webhooks.map((wh) => (
							<div
								key={wh.id}
								className="flex items-center gap-2 bg-secondary/30 rounded px-2.5 py-1.5"
							>
								<code className="text-xs text-foreground/80 font-mono truncate flex-1">
									{wh.url}
								</code>
								<span className="text-[10px] text-muted-foreground shrink-0">
									{wh.events.join(", ")}
								</span>
								<button
									onClick={() => handleDelete(wh.id)}
									className="p-1 text-muted-foreground/40 hover:text-destructive transition-colors shrink-0"
								>
									<Trash2 className="w-3 h-3" />
								</button>
							</div>
						))}
					</div>
				)}

				<div className="flex gap-2">
					<input
						type="url"
						value={newUrl}
						onChange={(e) => setNewUrl(e.target.value)}
						placeholder="https://example.com/webhook"
						onKeyDown={(e) => e.key === "Enter" && handleAdd()}
						className="flex-1 text-xs bg-secondary/50 border border-border rounded px-2.5 py-1.5 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-accent font-mono"
					/>
					<button
						onClick={handleAdd}
						disabled={!newUrl.trim() || adding}
						className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground disabled:opacity-40 hover:bg-accent/85 transition-colors"
					>
						<Plus className="w-3 h-3" />
						Add
					</button>
				</div>
			</div>
		</section>
	);
}

function CodeBlock({ label, code }: { label: string; code: string }) {
	const [copied, setCopied] = useState(false);
	const handleCopy = () => {
		navigator.clipboard.writeText(code);
		setCopied(true);
		setTimeout(() => setCopied(false), 1500);
	};
	return (
		<div>
			<p className="text-[10px] text-muted-foreground/60 mb-0.5">{label}</p>
			<div
				onClick={handleCopy}
				className="text-[11px] font-mono text-foreground/80 bg-secondary/40 rounded px-2.5 py-1.5 overflow-x-auto cursor-pointer hover:bg-secondary/60 transition-colors whitespace-nowrap"
				title="Click to copy"
			>
				{code}
				{copied && <span className="ml-2 text-accent text-[10px]">copied!</span>}
			</div>
		</div>
	);
}
