import {
	ArrowRight,
	Clock,
	KeyRound,
	Map as MapIcon,
	Scale,
	Send,
	ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import AuthModal from "@/features/auth/components/AuthModal";
import { Button } from "@/shared/ui";
import "./HomePage.css";

// lucide-react removed brand-mark icons (trademark policy), so we ship our own
// small GitHub mark. Matches the simple-icons / GitHub-octocat path.
function Github({
	className,
	"aria-hidden": ariaHidden,
}: {
	className?: string;
	"aria-hidden"?: boolean;
}) {
	return (
		<svg
			className={className}
			viewBox="0 0 24 24"
			fill="currentColor"
			aria-hidden={ariaHidden ?? true}
		>
			<path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.27-1.68-1.27-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.69 1.25 3.34.95.1-.74.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.04 0 0 .96-.31 3.16 1.18a10.94 10.94 0 0 1 5.75 0c2.2-1.49 3.16-1.18 3.16-1.18.62 1.58.23 2.75.11 3.04.74.81 1.18 1.84 1.18 3.1 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14 0 1.55-.01 2.79-.01 3.17 0 .31.21.68.8.56C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
		</svg>
	);
}

const GITHUB_REPO = "lanterno/beats";
const GITHUB_URL = `https://github.com/${GITHUB_REPO}`;
const REPO_RAW_API = `https://api.github.com/repos/${GITHUB_REPO}`;

// Vite injects this at build time when VITE_GIT_SHA is set (CI / Cloud Build).
// Falls back to "dev" locally so the footer never reads as fake metric.
const DEPLOY_SHA = (import.meta.env.VITE_GIT_SHA as string | undefined)?.slice(0, 7) ?? "dev";

type AuthHandler = (mode: "login" | "register-email") => void;

// ───────────────────────── helpers ──────────────────────────

function timeAgo(iso: string): string {
	const then = new Date(iso).getTime();
	const now = Date.now();
	const s = Math.max(0, Math.floor((now - then) / 1000));
	if (s < 60) return `${s}s ago`;
	const m = Math.floor(s / 60);
	if (m < 60) return `${m}m ago`;
	const h = Math.floor(m / 60);
	if (h < 24) return `${h}h ago`;
	const d = Math.floor(h / 24);
	return `${d}d ago`;
}

// ───────────────────────── nav ──────────────────────────

function Nav({ onSignIn }: { onSignIn: () => void }) {
	return (
		<nav className="homepage-nav">
			<div className="homepage-nav-inner">
				<a href="#top" className="homepage-wordmark">
					<Clock className="w-4 h-4 text-accent" aria-hidden />
					<span className="font-heading text-lg tracking-tight text-foreground">Beats</span>
				</a>
				<div className="homepage-nav-links">
					<a href="#surfaces" className="homepage-nav-link">
						Surfaces
					</a>
					<a href="#why" className="homepage-nav-link">
						Why Beats
					</a>
					<a
						href={GITHUB_URL}
						target="_blank"
						rel="noreferrer"
						className="homepage-nav-link homepage-nav-github"
						aria-label="View on GitHub"
					>
						<Github className="w-3.5 h-3.5" aria-hidden />
						<span>GitHub</span>
						<img
							src={`https://img.shields.io/github/stars/${GITHUB_REPO}?style=flat&label=&color=222&labelColor=222`}
							alt="stars"
							className="homepage-nav-stars"
							loading="lazy"
							width={36}
							height={16}
						/>
					</a>
					<button type="button" className="homepage-nav-signin" onClick={onSignIn}>
						Sign in
					</button>
				</div>
			</div>
		</nav>
	);
}

// ───────────────────────── hero ──────────────────────────

function GhBadgeRow() {
	return (
		<div className="homepage-badge-row" aria-label="Open source proof">
			<img
				src={`https://img.shields.io/badge/open%20source-MIT-2b8a3e?style=flat&logo=opensourceinitiative&logoColor=white`}
				alt="Open source: MIT"
				loading="lazy"
				width={120}
				height={20}
			/>
			<img
				src={`https://img.shields.io/github/stars/${GITHUB_REPO}?style=flat&logo=github&logoColor=fff&label=stars&color=444`}
				alt="GitHub stars"
				loading="lazy"
				width={80}
				height={20}
			/>
			<img
				src={`https://img.shields.io/github/last-commit/${GITHUB_REPO}?style=flat&logo=git&logoColor=fff&label=last%20commit&color=444`}
				alt="Last commit"
				loading="lazy"
				width={130}
				height={20}
			/>
		</div>
	);
}

function DaemonStatusCard() {
	// Static, honest mock — not animated, not randomized, not pretending to be live.
	// Demonstrates the *shape* of the daemon status UI a signed-in user would see.
	return (
		<figure className="homepage-daemon-card" aria-label="Beats daemon status, example">
			<div className="homepage-daemon-head">
				<div className="homepage-daemon-pulse" aria-hidden />
				<span className="homepage-daemon-tag">beatsd · active</span>
				<span className="homepage-daemon-repo">lanterno/beats</span>
			</div>
			<div className="homepage-daemon-body">
				<div className="homepage-daemon-stat">
					<span className="homepage-daemon-stat-label">Current beat</span>
					<span className="homepage-daemon-stat-value font-mono">00:38:12</span>
				</div>
				<div className="homepage-daemon-stat">
					<span className="homepage-daemon-stat-label">Flow score</span>
					<span className="homepage-daemon-stat-value font-mono">0.84</span>
				</div>
				<div className="homepage-daemon-stat">
					<span className="homepage-daemon-stat-label">Window</span>
					<span className="homepage-daemon-stat-value font-mono">11:42 → 12:20</span>
				</div>
			</div>
			<div className="homepage-daemon-heatmap" aria-hidden>
				{Array.from({ length: 3 }).map((_, row) => (
					<div className="homepage-daemon-heatmap-row" key={row}>
						{HEATMAP_3DAY[row].map((v, i) => (
							<span key={i} className="homepage-daemon-heatmap-cell" data-intensity={v} />
						))}
					</div>
				))}
			</div>
			<figcaption className="homepage-daemon-caption">
				beatsd auto-started this beat from VS Code activity, 2 minutes ago.
			</figcaption>
		</figure>
	);
}

// Hand-tuned, stable 3-day x 24-hour intensity pattern (0–4).
// No Math.random — the same image renders for every visitor, every load.
const HEATMAP_3DAY: number[][] = [
	[0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 4, 4, 2, 1, 3, 4, 4, 3, 2, 1, 1, 0, 0, 0],
	[0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 4, 3, 2, 2, 3, 4, 4, 3, 2, 1, 1, 0, 0],
	[0, 0, 0, 0, 0, 0, 1, 2, 4, 4, 4, 3, 1, 0, 2, 3, 4, 3, 2, 1, 0, 0, 0, 0],
];

function Hero({ onPrimary }: { onPrimary: () => void }) {
	return (
		<section id="top" className="homepage-hero">
			<div className="homepage-hero-inner">
				<div className="homepage-hero-text">
					<GhBadgeRow />
					<h1 className="homepage-hero-title">Your time, tracked while you work.</h1>
					<p className="homepage-hero-subtitle">
						Beats is a free, open-source rhythm system. A background daemon catches your sessions
						across your editor, desktop, and an optional wall clock — then a coach helps you review
						the week.
					</p>
					<div className="homepage-hero-cta">
						<Button size="lg" onClick={onPrimary} className="homepage-cta-primary">
							<KeyRound className="w-4 h-4" aria-hidden />
							<span>Sign in with passkey</span>
							<ArrowRight className="w-4 h-4" aria-hidden />
						</Button>
						<a
							href={GITHUB_URL}
							target="_blank"
							rel="noreferrer"
							className="homepage-cta-secondary"
						>
							<Github className="w-3.5 h-3.5" aria-hidden />
							<span>Open the repo on GitHub</span>
							<ArrowRight className="w-3.5 h-3.5" aria-hidden />
						</a>
					</div>
					<ul className="homepage-hero-trust" aria-label="Trust signals">
						<li>
							<KeyRound className="w-3 h-3" aria-hidden />
							Passkey-only sign-in
						</li>
						<li>
							<Scale className="w-3 h-3" aria-hidden />
							MIT-licensed
						</li>
						<li>
							<Send className="w-3 h-3" aria-hidden />
							Your data exports anytime
						</li>
					</ul>
				</div>
				<div className="homepage-hero-visual">
					<DaemonStatusCard />
				</div>
			</div>
		</section>
	);
}

// ─────────────────────── surface tour ───────────────────────

type Surface = {
	n: string;
	title: string;
	outcome: string;
	detail: string;
	sourceLabel: string;
	sourceHref: string;
	mock: React.ReactNode;
};

function WebMock() {
	const cells = HEATMAP_3DAY.flat().concat(HEATMAP_3DAY.flat().reverse());
	return (
		<div className="homepage-mock homepage-mock-web">
			<div className="homepage-mock-head">
				<span className="homepage-mock-dot" />
				<span className="homepage-mock-title">This week</span>
				<span className="homepage-mock-meta font-mono">42h 18m</span>
			</div>
			<div className="homepage-mock-body">
				<div className="homepage-mock-rhythm">
					{Array.from({ length: 24 }).map((_, i) => {
						const h = 8 + Math.abs(Math.sin((i / 24) * Math.PI * 2)) * 32;
						return (
							<span className="homepage-mock-rhythm-bar" key={i} style={{ height: `${h}px` }} />
						);
					})}
				</div>
				<div className="homepage-mock-projects">
					<ProjectRow color="accent" name="Beats" hrs="14.2" />
					<ProjectRow color="success" name="Writing" hrs="6.8" />
					<ProjectRow color="primary" name="Reading" hrs="4.1" />
				</div>
				<div className="homepage-mock-heatmap-week" aria-hidden>
					{cells.slice(0, 7 * 18).map((v, i) => (
						<span className="homepage-mock-cell" data-intensity={v} key={i} />
					))}
				</div>
			</div>
		</div>
	);
}

function ProjectRow({ color, name, hrs }: { color: string; name: string; hrs: string }) {
	return (
		<div className="homepage-mock-project">
			<span className={`homepage-mock-project-dot homepage-mock-color-${color}`} />
			<span className="homepage-mock-project-name">{name}</span>
			<span className="homepage-mock-project-hrs font-mono">{hrs}h</span>
		</div>
	);
}

function DaemonMock() {
	return (
		<div className="homepage-mock homepage-mock-daemon">
			<div className="homepage-mock-head">
				<span className="homepage-mock-dot" />
				<span className="homepage-mock-title font-mono">beatsd · running</span>
				<span className="homepage-mock-meta font-mono">v0.4.2</span>
			</div>
			<pre className="homepage-mock-term" aria-hidden>
				<span className="homepage-term-prompt">$</span> beatsd status --here
				{"\n"}
				<span className="homepage-term-ok">●</span> active beat · lanterno/beats
				{"\n"}
				{"  "}flow score <span className="homepage-term-num">0.84</span>
				{"\n"}
				{"  "}duration <span className="homepage-term-num">00:38:12</span>
				{"\n"}
				{"  "}started <span className="homepage-term-mut">11:42 (auto · vscode)</span>
				{"\n"}
				{"  "}last commit <span className="homepage-term-mut">2m ago</span>
				{"\n"}
				<span className="homepage-term-prompt">$</span>
				<span className="homepage-term-caret" />
			</pre>
		</div>
	);
}

function EditorMock() {
	return (
		<div className="homepage-mock homepage-mock-editor">
			<div className="homepage-mock-editor-side">
				<div className="homepage-mock-editor-tab">
					<Clock className="w-3 h-3 text-accent" aria-hidden />
					<span>Beats</span>
				</div>
				<div className="homepage-mock-editor-current">
					<span className="homepage-mock-editor-label">Current beat</span>
					<span className="homepage-mock-editor-timer font-mono">00:38:12</span>
					<span className="homepage-mock-editor-repo font-mono">lanterno/beats</span>
				</div>
				<div className="homepage-mock-editor-section">
					<span className="homepage-mock-editor-label">Recent</span>
					<EditorRow time="11:08" repo="lanterno/beats" />
					<EditorRow time="09:42" repo="lanterno/notes" />
					<EditorRow time="08:14" repo="lanterno/api" />
				</div>
			</div>
			<div className="homepage-mock-editor-status">
				<span className="homepage-mock-editor-status-dot" />
				<span className="font-mono">beats: 00:38:12 · 0.84</span>
			</div>
		</div>
	);
}

function EditorRow({ time, repo }: { time: string; repo: string }) {
	return (
		<div className="homepage-mock-editor-row">
			<span className="homepage-mock-editor-time font-mono">{time}</span>
			<span className="homepage-mock-editor-repo-small font-mono">{repo}</span>
		</div>
	);
}

function CompanionMock() {
	return (
		<div className="homepage-mock homepage-mock-companion">
			<div className="homepage-mock-phone">
				<div className="homepage-mock-phone-notch" />
				<div className="homepage-mock-phone-screen">
					<span className="homepage-mock-phone-title">Today</span>
					<div className="homepage-mock-mood-row">
						{["😴", "🙂", "😀", "🧘", "😶"].map((e, i) => (
							<button
								key={i}
								type="button"
								className={`homepage-mock-mood ${i === 2 ? "is-active" : ""}`}
								tabIndex={-1}
								aria-hidden
							>
								{e}
							</button>
						))}
					</div>
					<div className="homepage-mock-bio">
						<BioRow label="Sleep" value="7h 24m" source="HealthKit" />
						<BioRow label="HRV" value="58 ms" source="Oura" />
						<BioRow label="Steps" value="6,421" source="HealthKit" />
					</div>
					<div className="homepage-mock-phone-cta">
						<span className="font-mono">End of day · log in 1 tap</span>
					</div>
				</div>
			</div>
		</div>
	);
}

function BioRow({ label, value, source }: { label: string; value: string; source: string }) {
	return (
		<div className="homepage-mock-bio-row">
			<span className="homepage-mock-bio-label">{label}</span>
			<span className="homepage-mock-bio-value font-mono">{value}</span>
			<span className="homepage-mock-bio-source font-mono">{source}</span>
		</div>
	);
}

function WallClockMock() {
	return (
		<div className="homepage-mock homepage-mock-clock">
			<div className="homepage-mock-clock-face">
				<svg viewBox="0 0 120 120" width="160" height="160" aria-hidden>
					<title>Wall clock face</title>
					<circle cx="60" cy="60" r="56" className="homepage-clock-ring" />
					<circle cx="60" cy="60" r="48" className="homepage-clock-inner" />
					{Array.from({ length: 12 }).map((_, i) => {
						const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
						const x1 = 60 + Math.cos(a) * 44;
						const y1 = 60 + Math.sin(a) * 44;
						const x2 = 60 + Math.cos(a) * 50;
						const y2 = 60 + Math.sin(a) * 50;
						return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} className="homepage-clock-tick" />;
					})}
					<text
						x="60"
						y="58"
						className="homepage-clock-digits"
						textAnchor="middle"
						dominantBaseline="middle"
					>
						00:38
					</text>
					<text
						x="60"
						y="72"
						className="homepage-clock-sub"
						textAnchor="middle"
						dominantBaseline="middle"
					>
						beats · lanterno
					</text>
				</svg>
			</div>
			<div className="homepage-mock-clock-board">
				<span className="font-mono">esp32-s3 · oled 128×64</span>
				<span className="font-mono">firmware/wall-clock</span>
			</div>
		</div>
	);
}

const SURFACES: Surface[] = [
	{
		n: "1.0",
		title: "Web — review your rhythm",
		outcome:
			"Heatmap, flow score, weekly goals. The pieces you'd rebuild in a spreadsheet, sharper.",
		detail: "Real-time WebSocket sync · CSV/JSON export · keyboard-first",
		sourceLabel: "View ui/",
		sourceHref: `${GITHUB_URL}/tree/main/ui`,
		mock: <WebMock />,
	},
	{
		n: "2.0",
		title: "Daemon — beatsd watches your editor, starts your timer",
		outcome:
			"A 6 MB Go binary running quietly. Detects editor + git activity, auto-starts a beat, scores the flow.",
		detail: "Foreground or LaunchAgent · JSON output for shell pipelines",
		sourceLabel: "View daemon/",
		sourceHref: `${GITHUB_URL}/tree/main/daemon`,
		mock: <DaemonMock />,
	},
	{
		n: "3.0",
		title: "Editor — VS Code shows your current beat",
		outcome:
			"A status-bar timer and sidebar that surface the beat the daemon already started. No buttons to press.",
		detail: "Workspace heartbeats · Insights deep-link · zero config",
		sourceLabel: "View integrations/vscode-beats",
		sourceHref: `${GITHUB_URL}/tree/main/integrations/vscode-beats`,
		mock: <EditorMock />,
	},
	{
		n: "4.0",
		title: "Companion — mood, energy, sleep from your phone",
		outcome:
			"Flutter app on iOS and Android. Pulls from HealthKit, Health Connect, Fitbit, Oura — so end-of-day is one tap, not a survey.",
		detail: "Optional · biometrics never leave your account",
		sourceLabel: "View companion/",
		sourceHref: `${GITHUB_URL}/tree/main/companion`,
		mock: <CompanionMock />,
	},
	{
		n: "5.0",
		title: "Wall clock — hardware you can build yourself",
		outcome:
			"Open ESP32 firmware. Solder it on a Sunday. Watch your beat tick on a clock on your desk.",
		detail: "OLED 128×64 · favorites · weekly bars",
		sourceLabel: "View wall-clock/",
		sourceHref: `${GITHUB_URL}/tree/main/wall-clock`,
		mock: <WallClockMock />,
	},
];

function SurfaceTour() {
	return (
		<section id="surfaces" className="homepage-surfaces">
			<div className="homepage-section-head">
				<p className="homepage-section-eyebrow">Five surfaces, one rhythm.</p>
				<h2 className="homepage-section-title">
					Beats follows you across the tools you already use.
				</h2>
			</div>
			<div className="homepage-surfaces-list">
				{SURFACES.map((s, idx) => (
					<SurfaceStop key={s.n} surface={s} flipped={idx % 2 === 1} />
				))}
			</div>
		</section>
	);
}

function SurfaceStop({ surface, flipped }: { surface: Surface; flipped: boolean }) {
	return (
		<article
			className={`homepage-surface-stop ${flipped ? "is-flipped" : ""}`}
			aria-labelledby={`surface-${surface.n}`}
		>
			<div className="homepage-surface-text">
				<span className="homepage-surface-num font-mono">{surface.n}</span>
				<h3 className="homepage-surface-title" id={`surface-${surface.n}`}>
					{surface.title}
				</h3>
				<p className="homepage-surface-outcome">{surface.outcome}</p>
				<p className="homepage-surface-detail font-mono">{surface.detail}</p>
				<a
					href={surface.sourceHref}
					target="_blank"
					rel="noreferrer"
					className="homepage-surface-source"
				>
					<Github className="w-3.5 h-3.5" aria-hidden />
					{surface.sourceLabel}
					<ArrowRight className="w-3.5 h-3.5" aria-hidden />
				</a>
			</div>
			<div className="homepage-surface-mock">{surface.mock}</div>
		</article>
	);
}

// ───────────────────── why beats (contrasts) ─────────────────────

function WhyBeats() {
	return (
		<section id="why" className="homepage-why">
			<div className="homepage-section-head">
				<p className="homepage-section-eyebrow">Why Beats</p>
				<h2 className="homepage-section-title">Better than the three things you're using now.</h2>
			</div>
			<div className="homepage-why-grid">
				<Contrast
					label="vs. a spreadsheet"
					title="Better than a spreadsheet — because you'll forget."
					proof="Beats records on its own. The spreadsheet only knows the days you remembered to open it."
				/>
				<Contrast
					label="vs. a timer"
					title="Better than a timer — because flow doesn't pause to start one."
					proof="beatsd detects editor and git activity and starts the beat for you. No buttons, no toggl-style ritual."
				/>
				<Contrast
					label="vs. surveillance"
					title="Better than surveillance — because we don't watch you."
					proof="No screenshots. No keylogging. Your beats live in your account, exportable as CSV or JSON anytime."
				/>
			</div>
		</section>
	);
}

function Contrast({ label, title, proof }: { label: string; title: string; proof: string }) {
	return (
		<div className="homepage-contrast">
			<span className="homepage-contrast-label font-mono">{label}</span>
			<p className="homepage-contrast-title">{title}</p>
			<p className="homepage-contrast-proof">{proof}</p>
		</div>
	);
}

// ─────────────────── trust band (founder + commits + roadmap) ───────────────────

type Commit = { sha: string; message: string; author: string; date: string; url: string };

function ShippedThisWeek() {
	const [commits, setCommits] = useState<Commit[] | null>(null);
	const [errored, setErrored] = useState(false);

	useEffect(() => {
		const cacheKey = "beats:home:commits:v1";
		const cached = sessionStorage.getItem(cacheKey);
		if (cached) {
			try {
				setCommits(JSON.parse(cached));
				return;
			} catch {
				// fall through to fetch
			}
		}
		const ctrl = new AbortController();
		fetch(`${REPO_RAW_API}/commits?per_page=3`, {
			signal: ctrl.signal,
			headers: { Accept: "application/vnd.github+json" },
		})
			.then((r) => (r.ok ? r.json() : Promise.reject(new Error(`status ${r.status}`))))
			.then((rows: unknown) => {
				if (!Array.isArray(rows)) throw new Error("bad shape");
				const out: Commit[] = rows.slice(0, 3).map((r) => {
					const c = r as Record<string, unknown>;
					const commit = (c.commit ?? {}) as Record<string, unknown>;
					const author = (commit.author ?? {}) as Record<string, unknown>;
					return {
						sha: String((c.sha as string | undefined) ?? "").slice(0, 7),
						message: String(commit.message ?? "").split("\n")[0],
						author: String(author.name ?? "Ahmed"),
						date: String(author.date ?? new Date().toISOString()),
						url: String(c.html_url ?? GITHUB_URL),
					};
				});
				sessionStorage.setItem(cacheKey, JSON.stringify(out));
				setCommits(out);
			})
			.catch(() => setErrored(true));
		return () => ctrl.abort();
	}, []);

	return (
		<div className="homepage-trust-card homepage-trust-commits">
			<div className="homepage-trust-card-head">
				<Clock className="w-3.5 h-3.5 text-accent" aria-hidden />
				<span>Shipped recently</span>
			</div>
			{errored && (
				<a
					href={`${GITHUB_URL}/commits/main`}
					target="_blank"
					rel="noreferrer"
					className="homepage-commit-empty"
				>
					See latest commits on GitHub →
				</a>
			)}
			{!errored && !commits && (
				<>
					<CommitSkeleton />
					<CommitSkeleton />
					<CommitSkeleton />
				</>
			)}
			{commits?.map((c) => (
				<a key={c.sha} href={c.url} target="_blank" rel="noreferrer" className="homepage-commit">
					<span className="homepage-commit-sha font-mono">{c.sha}</span>
					<span className="homepage-commit-msg">{c.message}</span>
					<span className="homepage-commit-meta font-mono">{timeAgo(c.date)}</span>
				</a>
			))}
		</div>
	);
}

function CommitSkeleton() {
	return (
		<div className="homepage-commit homepage-commit-skel" aria-hidden>
			<span className="homepage-commit-sha font-mono">·······</span>
			<span className="homepage-commit-msg" />
			<span className="homepage-commit-meta font-mono">·</span>
		</div>
	);
}

function FounderCard() {
	return (
		<div className="homepage-trust-card homepage-trust-founder">
			<div className="homepage-trust-card-head">
				<KeyRound className="w-3.5 h-3.5 text-accent" aria-hidden />
				<span>Built by one person</span>
			</div>
			<div className="homepage-founder-avatar" aria-hidden>
				<span className="font-heading">A</span>
			</div>
			<p className="homepage-founder-quote">
				“I built Beats because I wanted to know where my hours actually went. Not for a manager —
				for me.”
			</p>
			<div className="homepage-founder-meta">
				<span className="homepage-founder-name">Ahmed Elghareeb</span>
				<a
					href="https://github.com/lanterno"
					target="_blank"
					rel="noreferrer"
					className="homepage-founder-link font-mono"
				>
					@lanterno
				</a>
			</div>
		</div>
	);
}

function RoadmapCard() {
	return (
		<a
			href={`${GITHUB_URL}/issues`}
			target="_blank"
			rel="noreferrer"
			className="homepage-trust-card homepage-trust-roadmap"
		>
			<div className="homepage-trust-card-head">
				<MapIcon className="w-3.5 h-3.5 text-accent" aria-hidden />
				<span>Roadmap, in public</span>
			</div>
			<p className="homepage-roadmap-text">
				Every open issue and milestone lives on GitHub. File a request, vote, or open a PR.
			</p>
			<span className="homepage-roadmap-link font-mono">
				View issues
				<ArrowRight className="w-3.5 h-3.5" aria-hidden />
			</span>
		</a>
	);
}

function TrustBand() {
	return (
		<section className="homepage-trust">
			<div className="homepage-trust-grid">
				<FounderCard />
				<ShippedThisWeek />
				<RoadmapCard />
			</div>
		</section>
	);
}

// ─────────────────── objection killer row ───────────────────

function ObjectionRow() {
	return (
		<section className="homepage-objections" aria-label="Objection answers">
			<ul className="homepage-objections-row">
				<li>
					<a href="#why" className="homepage-objection">
						<KeyRound className="w-3.5 h-3.5" aria-hidden />
						<span>Passkey-only sign-in</span>
						<span className="homepage-objection-sub">No passwords stored, ever.</span>
					</a>
				</li>
				<li>
					<a
						href={`${GITHUB_URL}/blob/main/LICENSE`}
						target="_blank"
						rel="noreferrer"
						className="homepage-objection"
					>
						<Scale className="w-3.5 h-3.5" aria-hidden />
						<span>Open source — MIT</span>
						<span className="homepage-objection-sub">Read every line on GitHub.</span>
					</a>
				</li>
				<li>
					<a
						href={`${GITHUB_URL}/tree/main/api/src/beats/api/routes`}
						target="_blank"
						rel="noreferrer"
						className="homepage-objection"
					>
						<Send className="w-3.5 h-3.5" aria-hidden />
						<span>Export your data anytime</span>
						<span className="homepage-objection-sub">CSV or JSON, on demand.</span>
					</a>
				</li>
				<li>
					<a
						href="https://github.com/lanterno"
						target="_blank"
						rel="noreferrer"
						className="homepage-objection"
					>
						<ShieldCheck className="w-3.5 h-3.5" aria-hidden />
						<span>Funded by the founder</span>
						<span className="homepage-objection-sub">Not by your data.</span>
					</a>
				</li>
			</ul>
		</section>
	);
}

// ─────────────────── final CTA ───────────────────

function FinalCta({ onPrimary }: { onPrimary: () => void }) {
	return (
		<section className="homepage-final-cta">
			<h2 className="homepage-section-title">Start tracking the way you actually work.</h2>
			<p className="homepage-final-sub">
				Free. Open source. Passkey-only. Your data, your hardware, your call.
			</p>
			<div className="homepage-final-actions">
				<Button size="lg" onClick={onPrimary} className="homepage-cta-primary">
					<KeyRound className="w-4 h-4" aria-hidden />
					<span>Sign in with passkey</span>
					<ArrowRight className="w-4 h-4" aria-hidden />
				</Button>
				<a
					href={`${GITHUB_URL}#readme`}
					target="_blank"
					rel="noreferrer"
					className="homepage-cta-secondary"
				>
					<Github className="w-3.5 h-3.5" aria-hidden />
					<span>or clone the repo</span>
					<ArrowRight className="w-3.5 h-3.5" aria-hidden />
				</a>
			</div>
		</section>
	);
}

// ─────────────────── footer ───────────────────

function FooterNew() {
	return (
		<footer className="homepage-footer">
			<div className="homepage-footer-cols">
				<FooterCol
					title="Product"
					links={[
						{ label: "Surfaces", href: "#surfaces" },
						{ label: "Web app", href: "/" },
						{
							label: "VS Code extension",
							href: `${GITHUB_URL}/tree/main/integrations/vscode-beats`,
						},
						{ label: "Wall clock firmware", href: `${GITHUB_URL}/tree/main/wall-clock` },
					]}
				/>
				<FooterCol
					title="Open source"
					links={[
						{ label: "GitHub repo", href: GITHUB_URL },
						{ label: "MIT License", href: `${GITHUB_URL}/blob/main/LICENSE` },
						{ label: "Roadmap", href: `${GITHUB_URL}/issues` },
						{ label: "Changelog", href: `${GITHUB_URL}/commits/main` },
					]}
				/>
				<FooterCol
					title="Legal"
					links={[
						{ label: "Privacy", href: `${GITHUB_URL}#privacy` },
						{ label: "Data handling", href: `${GITHUB_URL}#data` },
						{ label: "Contact", href: "mailto:ahmed.elghareeb@proton.me" },
					]}
				/>
				<FooterCol
					title="Built by Ahmed"
					links={[
						{ label: "@lanterno on GitHub", href: "https://github.com/lanterno" },
						{ label: "Email", href: "mailto:ahmed.elghareeb@proton.me" },
					]}
				/>
			</div>
			<div className="homepage-footer-bottom">
				<div className="homepage-footer-mark">
					<Clock className="w-3 h-3 text-accent" aria-hidden />
					<span className="font-heading">Beats</span>
					<span className="homepage-footer-sha font-mono" aria-label="Deployed commit SHA">
						build · {DEPLOY_SHA}
					</span>
				</div>
				<p className="homepage-footer-tag">Made with care, not for sale.</p>
			</div>
		</footer>
	);
}

function FooterCol({ title, links }: { title: string; links: { label: string; href: string }[] }) {
	return (
		<div className="homepage-footer-col">
			<p className="homepage-footer-col-title font-mono">{title}</p>
			<ul>
				{links.map((l) => (
					<li key={l.label}>
						<a
							href={l.href}
							target={
								l.href.startsWith("http") || l.href.startsWith("mailto:") ? "_blank" : undefined
							}
							rel="noreferrer"
						>
							{l.label}
						</a>
					</li>
				))}
			</ul>
		</div>
	);
}

// ───────────────────── homepage root ─────────────────────

export default function HomePage() {
	const [authOpen, setAuthOpen] = useState(false);
	const [authMode, setAuthMode] = useState<"login" | "register-email">("register-email");

	const open: AuthHandler = (mode) => {
		setAuthMode(mode);
		setAuthOpen(true);
	};
	const onSignIn = () => open("login");
	const onPrimary = () => open("register-email");

	return (
		<div className="homepage-root">
			<Nav onSignIn={onSignIn} />
			<Hero onPrimary={onPrimary} />
			<SurfaceTour />
			<WhyBeats />
			<TrustBand />
			<ObjectionRow />
			<FinalCta onPrimary={onPrimary} />
			<FooterNew />
			<AuthModal open={authOpen} onClose={() => setAuthOpen(false)} initialMode={authMode} />
		</div>
	);
}
