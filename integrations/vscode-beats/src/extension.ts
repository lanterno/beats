import * as vscode from "vscode";
import { buildInsightsUrl } from "./insightsUrl";
import {
  formatStatusBar,
  type FlowSummary,
  type HealthSummary,
} from "./statusBar";

interface Heartbeat {
  editor: "vscode";
  repo: string | null;
  branch: string | null;
  language: string | null;
  timestamp: string;
}

interface GitAPI {
  repositories: Array<{
    rootUri: vscode.Uri;
    state: { HEAD?: { name?: string } };
  }>;
}

let timer: NodeJS.Timeout | undefined;
let healthTimer: NodeJS.Timeout | undefined;
let statusBar: vscode.StatusBarItem | undefined;

export function activate(context: vscode.ExtensionContext): void {
  start();

  // Restart the loop when settings change so interval / port edits take
  // effect without a full reload.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("beats")) {
        stop();
        start();
      }
    })
  );

  // ⌘⇧P → "Beats: Open Insights" — opens the configured web URL in
  // the system browser, pre-filtered to the current workspace's repo
  // path so the user lands on a view of *this* project's flow rather
  // than the unfiltered default. Mirrors the click-to-filter chip on
  // the web Insights page; closes the loop between heartbeat producer
  // and analytics consumer in the same editor.
  context.subscriptions.push(
    vscode.commands.registerCommand("beats.openInsights", openInsights)
  );

  // Status-bar item polling /health on a 60s interval. Click runs
  // beats.openInsights — same destination as ⌘⇧P, just discoverable
  // without invoking the command palette. Hidden when
  // beats.statusBar.enabled is false (some users prefer a quiet bar).
  startStatusBar(context);

  context.subscriptions.push({ dispose: stop });
}

export function deactivate(): void {
  stop();
}

function start(): void {
  const cfg = vscode.workspace.getConfiguration("beats");
  if (!cfg.get<boolean>("enabled", true)) return;

  const intervalSec = Math.max(5, cfg.get<number>("heartbeatIntervalSeconds", 30));
  // Send one immediately so the daemon has a fresh signal at activation,
  // then on the configured cadence afterwards.
  void sendHeartbeat();
  timer = setInterval(() => void sendHeartbeat(), intervalSec * 1000);
}

function stop(): void {
  if (timer) {
    clearInterval(timer);
    timer = undefined;
  }
  if (healthTimer) {
    clearInterval(healthTimer);
    healthTimer = undefined;
  }
  if (statusBar) {
    statusBar.dispose();
    statusBar = undefined;
  }
}

function startStatusBar(context: vscode.ExtensionContext): void {
  const cfg = vscode.workspace.getConfiguration("beats");
  if (!cfg.get<boolean>("statusBar.enabled", true)) return;

  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.command = "beats.openInsights";
  statusBar.show();
  context.subscriptions.push(statusBar);

  void refreshHealth();
  // 60s cadence — same as the daemon's heartbeat-of-heartbeats. The
  // health endpoint is cheap (no API round-trip, just an in-memory
  // snapshot) so we don't need to hold off when VS Code is unfocused.
  healthTimer = setInterval(() => void refreshHealth(), 60_000);
}

async function refreshHealth(): Promise<void> {
  if (!statusBar) return;
  const cfg = vscode.workspace.getConfiguration("beats");
  const port = cfg.get<number>("daemonPort", 37499);
  let health: HealthSummary | null = null;
  let summary: FlowSummary | null = null;
  try {
    const resp = await fetch(`http://127.0.0.1:${port}/health`, {
      signal: AbortSignal.timeout(1000),
    });
    if (resp.ok) {
      const body = (await resp.json()) as {
        ok: boolean;
        version: string;
        uptime_sec: number;
        editor_count: number;
      };
      health = {
        ok: body.ok,
        version: body.version,
        uptimeSec: body.uptime_sec,
        editorCount: body.editor_count,
      };
    }
  } catch {
    // Daemon offline — fall through to formatStatusBar(null).
  }

  // Only chase the summary when health is good. Saves a network call
  // when the daemon is offline (where the second fetch would block on
  // the same TCP RST) and keeps the offline-state code path tight.
  if (health?.ok) {
    try {
      const resp = await fetch(`http://127.0.0.1:${port}/summary`, {
        signal: AbortSignal.timeout(2000),
      });
      if (resp.ok) {
        const body = (await resp.json()) as {
          count: number;
          avg: number;
          peak: number;
          top_repo: { key: string } | null;
          top_language: { key: string } | null;
        };
        summary = {
          count: body.count,
          avg: body.avg,
          peak: body.peak,
          topRepo: body.top_repo?.key,
          topLanguage: body.top_language?.key,
        };
      }
      // 503 (no fetcher) and 502 (upstream error) intentionally fall
      // through with summary=null — the status bar still shows the
      // connected indicator, just without the score.
    } catch {
      // Network glitch — same fallthrough.
    }
  }

  const { text, tooltip } = formatStatusBar(health, summary);
  statusBar.text = text;
  statusBar.tooltip = tooltip;
}

async function sendHeartbeat(): Promise<void> {
  // Skip while VS Code is in the background — the user isn't editing here,
  // and the daemon's frontmost-app detection is the better signal anyway.
  if (!vscode.window.state.focused) return;

  const cfg = vscode.workspace.getConfiguration("beats");
  const port = cfg.get<number>("daemonPort", 37499);
  const sendBranch = cfg.get<boolean>("privacy.sendBranch", true);

  const heartbeat: Heartbeat = {
    editor: "vscode",
    repo: workspaceRoot(),
    branch: sendBranch ? gitBranch() : null,
    language: vscode.window.activeTextEditor?.document.languageId ?? null,
    timestamp: new Date().toISOString(),
  };

  // Fire-and-forget. If the daemon isn't running we don't surface anything
  // to the user — the extension is silently no-op when there's no listener.
  try {
    await fetch(`http://127.0.0.1:${port}/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(heartbeat),
      signal: AbortSignal.timeout(1000),
    });
  } catch {
    // Expected when the daemon is offline. Don't log.
  }
}

function workspaceRoot(): string | null {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return folder ? folder.uri.fsPath : null;
}

/**
 * Opens the Beats Insights page in the system browser. When a workspace
 * is open we pass `?repo=<absolute path>` so the page lands on the
 * already-filtered view — same URL scheme the page uses for its
 * click-to-filter chip persistence.
 */
async function openInsights(): Promise<void> {
  const cfg = vscode.workspace.getConfiguration("beats");
  const base = cfg.get<string>("webUrl", "http://localhost:8080");
  const url = buildInsightsUrl(base, workspaceRoot());
  await vscode.env.openExternal(vscode.Uri.parse(url));
}

function gitBranch(): string | null {
  // The built-in vscode.git extension exposes a typed API at version 1.
  const ext = vscode.extensions.getExtension<{ getAPI(version: 1): GitAPI }>("vscode.git");
  if (!ext?.isActive) return null;
  try {
    const api = ext.exports.getAPI(1);
    const root = workspaceRoot();
    if (!root) return null;
    const repo = api.repositories.find((r) => r.rootUri.fsPath === root);
    return repo?.state.HEAD?.name ?? null;
  } catch {
    return null;
  }
}
