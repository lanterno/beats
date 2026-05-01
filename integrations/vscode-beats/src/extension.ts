import * as vscode from "vscode";
import { buildInsightsUrl } from "./insightsUrl";

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
