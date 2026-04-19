/**
 * Settings Page
 * Appearance, data export, API info, and developer tools.
 */

import {
	Calendar,
	Cpu,
	Download,
	ExternalLink,
	Eye,
	FileJson,
	FileSpreadsheet,
	Fingerprint,
	Github,
	Heart,
	Moon,
	Palette,
	Plus,
	CircleDot,
	Rows3,
	Sun,
	Terminal,
	Trash2,
	Upload,
	Webhook,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
	fetchCalendarAuthUrl,
	useCalendarStatus,
	useConnectCalendar,
	useDisconnectCalendar,
} from "@/entities/calendar";
import {
	fetchGitHubAuthUrl,
	useConnectGitHub,
	useDisconnectGitHub,
	useGitHubStatus,
} from "@/entities/github";
import { useProjects } from "@/entities/project";
import type { CredentialInfo } from "@/features/auth";
import { getSessionToken } from "@/features/auth/stores/authStore";
import { del, get, post } from "@/shared/api";
import { config } from "@/shared/config";
import { COLOR_MODES, DENSITIES, THEMES, useOAuthCallback, useTheme } from "@/shared/lib";
import { CoachUsage } from "./CoachUsage";

export default function Settings() {
	const { data: projects } = useProjects();
	const [importing, setImporting] = useState(false);
	const { theme, setTheme, mode, setMode, density, setDensity } = useTheme();

	const apiBase = config.apiBaseUrl;

	const downloadFile = async (url: string, filename: string) => {
		try {
			const token = getSessionToken();
			const res = await fetch(`${apiBase}${url}`, {
				headers: token ? { Authorization: `Bearer ${token}` } : {},
			});
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
			const token = getSessionToken();
			const res = await fetch(`${apiBase}/api/export/import`, {
				method: "POST",
				headers: token ? { Authorization: `Bearer ${token}` } : {},
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

function CalendarSection() {
	const { data: status } = useCalendarStatus();
	const connectMutation = useConnectCalendar();
	const disconnectMutation = useDisconnectCalendar();
	const connectCalendar = connectMutation.mutate;

	useOAuthCallback(
		"calendar",
		connectCalendar,
		() => toast.success("Google Calendar connected"),
		() => toast.error("Failed to connect calendar"),
	);

	const handleConnect = async () => {
		try {
			const url = await fetchCalendarAuthUrl();
			window.location.href = url;
		} catch {
			toast.error("Failed to get auth URL — check Google OAuth credentials");
		}
	};

	const handleDisconnect = () => {
		disconnectMutation.mutate(undefined, {
			onSuccess: () => toast.success("Calendar disconnected"),
			onError: () => toast.error("Failed to disconnect"),
		});
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Calendar className="w-4 h-4 text-accent" />
				Google Calendar
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Connect Google Calendar to see events alongside your tracked sessions. Read-only access —
					Beats never modifies your calendar.
				</p>
				{status?.connected ? (
					<div className="flex items-center gap-3">
						<span className="text-xs text-accent font-medium">Connected</span>
						<button
							onClick={handleDisconnect}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
						>
							Disconnect
						</button>
					</div>
				) : (
					<button
						onClick={handleConnect}
						className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
					>
						Connect Google Calendar
					</button>
				)}
			</div>
		</section>
	);
}

function GitHubSection() {
	const { data: status } = useGitHubStatus();
	const connectMutation = useConnectGitHub();
	const disconnectMutation = useDisconnectGitHub();
	const connectGitHub = connectMutation.mutate;

	useOAuthCallback(
		"github",
		connectGitHub,
		() => toast.success("GitHub connected"),
		() => toast.error("Failed to connect GitHub"),
	);

	const handleConnect = async () => {
		try {
			const url = await fetchGitHubAuthUrl();
			window.location.href = url;
		} catch {
			toast.error("Failed to get auth URL — check GitHub OAuth credentials");
		}
	};

	const handleDisconnect = () => {
		disconnectMutation.mutate(undefined, {
			onSuccess: () => toast.success("GitHub disconnected"),
			onError: () => toast.error("Failed to disconnect"),
		});
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Github className="w-4 h-4 text-accent" />
				GitHub
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Connect GitHub to see commit activity alongside your tracked sessions. Link a repo to a
					project in its settings to enable correlation.
				</p>
				{status?.connected ? (
					<div className="flex items-center gap-3">
						<span className="text-xs text-accent font-medium">
							Connected as {status.github_username}
						</span>
						<button
							onClick={handleDisconnect}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
						>
							Disconnect
						</button>
					</div>
				) : (
					<button
						onClick={handleConnect}
						className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
					>
						Connect GitHub
					</button>
				)}
			</div>
		</section>
	);
}

function FitbitSection() {
	const [status, setStatus] = useState<{ connected: boolean; fitbit_user_id?: string } | null>(
		null,
	);
	const [loading, setLoading] = useState(false);

	const fetchStatus = useCallback(async () => {
		try {
			const data = await get<{ connected: boolean; fitbit_user_id?: string }>("/api/fitbit/status");
			setStatus(data);
		} catch {
			// non-critical
		}
	}, []);

	useEffect(() => {
		fetchStatus();
	}, [fetchStatus]);

	// Handle OAuth callback
	useEffect(() => {
		const params = new URLSearchParams(window.location.search);
		if (params.get("fitbit") === "callback") {
			const code = params.get("code");
			if (code) {
				post(`/api/fitbit/connect?code=${encodeURIComponent(code)}`)
					.then(() => {
						toast.success("Fitbit connected");
						fetchStatus();
						window.history.replaceState({}, "", window.location.pathname);
					})
					.catch(() => toast.error("Failed to connect Fitbit"));
			}
		}
	}, [fetchStatus]);

	const handleConnect = async () => {
		setLoading(true);
		try {
			const data = await get<{ url: string }>("/api/fitbit/auth-url");
			window.location.href = data.url;
		} catch {
			toast.error("Failed to get Fitbit auth URL");
			setLoading(false);
		}
	};

	const handleDisconnect = async () => {
		try {
			await del("/api/fitbit/disconnect");
			setStatus({ connected: false });
			toast.success("Fitbit disconnected");
		} catch {
			toast.error("Failed to disconnect Fitbit");
		}
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Heart className="w-4 h-4 text-accent" />
				Fitbit
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Connect Fitbit to sync sleep, HRV, resting heart rate, and activity data for
					recovery-aware coaching.
				</p>
				{status?.connected ? (
					<div className="flex items-center gap-3">
						<span className="text-xs text-accent font-medium">
							Connected{status.fitbit_user_id ? ` (${status.fitbit_user_id})` : ""}
						</span>
						<button
							type="button"
							onClick={handleDisconnect}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
						>
							Disconnect
						</button>
					</div>
				) : (
					<button
						type="button"
						onClick={handleConnect}
						disabled={loading}
						className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors disabled:opacity-50"
					>
						{loading ? "Connecting..." : "Connect Fitbit"}
					</button>
				)}
			</div>
		</section>
	);
}

function OuraSection() {
	const [status, setStatus] = useState<{ connected: boolean; oura_user_id?: string } | null>(null);
	const [pat, setPat] = useState("");
	const [connecting, setConnecting] = useState(false);

	const fetchStatus = useCallback(async () => {
		try {
			const data = await get<{ connected: boolean; oura_user_id?: string }>("/api/oura/status");
			setStatus(data);
		} catch {
			// non-critical
		}
	}, []);

	useEffect(() => {
		fetchStatus();
	}, [fetchStatus]);

	const handleConnect = async () => {
		if (!pat.trim()) return;
		setConnecting(true);
		try {
			await post("/api/oura/connect", { access_token: pat.trim() });
			setPat("");
			toast.success("Oura connected");
			fetchStatus();
		} catch {
			toast.error("Invalid Oura token — check and try again");
		} finally {
			setConnecting(false);
		}
	};

	const handleDisconnect = async () => {
		try {
			await del("/api/oura/disconnect");
			setStatus({ connected: false });
			toast.success("Oura disconnected");
		} catch {
			toast.error("Failed to disconnect Oura");
		}
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<CircleDot className="w-4 h-4 text-accent" />
				Oura
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Connect your Oura CircleDot to sync sleep, readiness, and HRV data. Get a personal access token
					from{" "}
					<a
						href="https://cloud.ouraring.com/personal-access-tokens"
						target="_blank"
						rel="noopener noreferrer"
						className="text-accent hover:underline"
					>
						cloud.ouraring.com
					</a>
					.
				</p>
				{status?.connected ? (
					<div className="flex items-center gap-3">
						<span className="text-xs text-accent font-medium">Connected</span>
						<button
							type="button"
							onClick={handleDisconnect}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
						>
							Disconnect
						</button>
					</div>
				) : (
					<div className="flex gap-2">
						<input
							type="password"
							value={pat}
							onChange={(e) => setPat(e.target.value)}
							placeholder="Oura personal access token"
							className="flex-1 px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/20 text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-accent"
						/>
						<button
							type="button"
							onClick={handleConnect}
							disabled={connecting || !pat.trim()}
							className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors disabled:opacity-50"
						>
							{connecting ? "Connecting..." : "Connect"}
						</button>
					</div>
				)}
			</div>
		</section>
	);
}

interface DeviceRegistrationInfo {
	id: string;
	device_id: string;
	device_name: string | null;
	created_at: string;
	last_seen: string | null;
}

function DaemonSection() {
	const [code, setCode] = useState<string | null>(null);
	const [loading, setLoading] = useState(false);
	const [devices, setDevices] = useState<DeviceRegistrationInfo[]>([]);
	const [revoking, setRevoking] = useState<string | null>(null);

	const fetchDevices = useCallback(async () => {
		try {
			const data = await get<DeviceRegistrationInfo[]>("/api/device/registrations");
			setDevices(data);
		} catch {
			// Silently ignore — devices list is non-critical
		}
	}, []);

	useEffect(() => {
		fetchDevices();
	}, [fetchDevices]);

	const handleGenerateCode = async () => {
		setLoading(true);
		try {
			const data = await post<{ code: string; expires_in_seconds: number }>(
				"/api/device/pair/code",
			);
			setCode(data.code);
			toast.success("Pairing code generated");
		} catch {
			toast.error("Failed to generate pairing code");
		} finally {
			setLoading(false);
		}
	};

	const handleRevoke = async (deviceId: string) => {
		setRevoking(deviceId);
		try {
			await del(`/api/device/registrations/${deviceId}`);
			setDevices((prev) => prev.filter((d) => d.device_id !== deviceId));
			toast.success("Device revoked");
		} catch {
			toast.error("Failed to revoke device");
		} finally {
			setRevoking(null);
		}
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Cpu className="w-4 h-4 text-accent" />
				Daemon
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-4">
				<p className="text-xs text-muted-foreground">
					Pair the <code className="text-accent">beatsd</code> daemon to this account for ambient
					flow tracking. Run <code className="text-accent">beatsd pair &lt;code&gt;</code> within 5
					minutes.
				</p>

				{code ? (
					<div className="space-y-2">
						<div className="font-mono text-2xl tracking-[0.3em] text-accent font-bold">{code}</div>
						<p className="text-[10px] text-muted-foreground">Expires in 5 minutes. One-time use.</p>
						<button
							type="button"
							onClick={() => setCode(null)}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/50 transition-colors"
						>
							Dismiss
						</button>
					</div>
				) : (
					<button
						type="button"
						onClick={handleGenerateCode}
						disabled={loading}
						className="px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors disabled:opacity-50"
					>
						{loading ? "Generating..." : "Pair new device"}
					</button>
				)}

				{devices.length > 0 && (
					<div className="space-y-2 pt-2 border-t border-border/50">
						<p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider">
							Paired devices
						</p>
						{devices.map((d) => (
							<div key={d.device_id} className="flex items-center justify-between text-xs">
								<div>
									<span className="text-foreground">{d.device_name || "Unnamed device"}</span>
									{d.last_seen && (
										<span className="text-muted-foreground ml-2">
											last seen {new Date(d.last_seen).toLocaleDateString()}
										</span>
									)}
								</div>
								<button
									type="button"
									onClick={() => handleRevoke(d.device_id)}
									disabled={revoking === d.device_id}
									className="px-2 py-1 text-[10px] rounded border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors disabled:opacity-50"
								>
									{revoking === d.device_id ? "Revoking..." : "Revoke"}
								</button>
							</div>
						))}
					</div>
				)}
			</div>
		</section>
	);
}

interface SignalSummaryInfo {
	id: string;
	hour: string;
	categories: Record<string, number>;
	total_samples: number;
	idle_samples: number;
}

function DaemonPrivacySection() {
	const [summaries, setSummaries] = useState<SignalSummaryInfo[]>([]);
	const [deleting, setDeleting] = useState(false);
	const [confirmDelete, setConfirmDelete] = useState(false);

	const fetchSummaries = useCallback(async () => {
		try {
			const now = new Date();
			const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
			const data = await get<SignalSummaryInfo[]>(
				`/api/signals/summaries?start=${dayAgo.toISOString()}&end=${now.toISOString()}`,
			);
			setSummaries(data);
		} catch {
			// non-critical
		}
	}, []);

	useEffect(() => {
		fetchSummaries();
	}, [fetchSummaries]);

	// Aggregate categories across all summaries
	const categoryTotals: Record<string, number> = {};
	let totalSamples = 0;
	let idleSamples = 0;
	for (const s of summaries) {
		totalSamples += s.total_samples;
		idleSamples += s.idle_samples;
		for (const [cat, count] of Object.entries(s.categories)) {
			categoryTotals[cat] = (categoryTotals[cat] || 0) + count;
		}
	}

	const handleDeleteAll = async () => {
		setDeleting(true);
		try {
			await del("/api/signals/all");
			setSummaries([]);
			setConfirmDelete(false);
			toast.success("All signal data deleted");
		} catch {
			toast.error("Failed to delete signals");
		} finally {
			setDeleting(false);
		}
	};

	const handleExport = async () => {
		try {
			const now = new Date();
			const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
			const data = await get<SignalSummaryInfo[]>(
				`/api/signals/summaries?start=${dayAgo.toISOString()}&end=${now.toISOString()}`,
			);
			const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
			const url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = `beats-signals-${now.toISOString().slice(0, 10)}.json`;
			a.click();
			URL.revokeObjectURL(url);
		} catch {
			toast.error("Failed to export signals");
		}
	};

	const sortedCategories = Object.entries(categoryTotals).sort(([, a], [, b]) => b - a);

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Eye className="w-4 h-4 text-accent" />
				Signal Privacy
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-4">
				<p className="text-xs text-muted-foreground">
					The daemon sends only aggregated category counts and flow scores. No raw content,
					keystrokes, or window titles are ever transmitted.
				</p>

				{totalSamples > 0 ? (
					<div className="space-y-3">
						<p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider">
							Last 24 hours
						</p>
						<div className="grid grid-cols-2 gap-2">
							{sortedCategories.map(([cat, count]) => (
								<div key={cat} className="flex items-center justify-between text-xs">
									<span className="text-foreground capitalize">{cat}</span>
									<span className="text-muted-foreground tabular-nums">{count} samples</span>
								</div>
							))}
							<div className="flex items-center justify-between text-xs">
								<span className="text-foreground">Idle</span>
								<span className="text-muted-foreground tabular-nums">{idleSamples} samples</span>
							</div>
						</div>
						<p className="text-[10px] text-muted-foreground">
							Total: {totalSamples} samples across {summaries.length} hours
						</p>
					</div>
				) : (
					<p className="text-xs text-muted-foreground/60">No signal data in the last 24 hours.</p>
				)}

				<div className="flex gap-2 pt-2 border-t border-border/50">
					<button
						type="button"
						onClick={handleExport}
						className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/50 transition-colors"
					>
						Export 24h (JSON)
					</button>
					{confirmDelete ? (
						<div className="flex items-center gap-2">
							<button
								type="button"
								onClick={handleDeleteAll}
								disabled={deleting}
								className="px-3 py-1.5 text-xs rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
							>
								{deleting ? "Deleting..." : "Confirm delete"}
							</button>
							<button
								type="button"
								onClick={() => setConfirmDelete(false)}
								className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/50 transition-colors"
							>
								Cancel
							</button>
						</div>
					) : (
						<button
							type="button"
							onClick={() => setConfirmDelete(true)}
							className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary/30 text-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
						>
							Delete all signals
						</button>
					)}
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
