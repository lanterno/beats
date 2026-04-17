import {
	ArrowDown,
	CalendarRange,
	CheckCircle,
	Clock,
	LayoutGrid,
	MonitorSmartphone,
	SmilePlus,
	TrendingUp,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import AuthModal from "@/features/auth/components/AuthModal";
import { useCountUp } from "@/shared/lib/useCountUp";
import { Button, Reveal } from "@/shared/ui";
import "./HomePage.css";

const FEATURES = [
	{
		icon: LayoutGrid,
		title: "Project-Based Tracking",
		description:
			"Organize time by project with color-coded categories. Set weekly goals as targets or caps — stay focused on what matters.",
	},
	{
		icon: TrendingUp,
		title: "Daily Rhythm Insights",
		description:
			"Visualize when you're most productive. Discover your natural patterns with hour-by-hour activity breakdowns.",
	},
	{
		icon: CheckCircle,
		title: "Weekly Goals",
		description:
			"Set time targets for each project. Track progress with visual goal rings that update in real-time as you work.",
	},
	{
		icon: CalendarRange,
		title: "Contribution Heatmap",
		description:
			"GitHub-style heatmap of your work year. See streaks, gaps, and long-term consistency at a glance.",
	},
	{
		icon: SmilePlus,
		title: "Mood & Energy Tracking",
		description:
			"Log how you feel at end-of-day. Correlate mood with productivity to understand what drives your best work.",
	},
	{
		icon: MonitorSmartphone,
		title: "Wall Clock Sync",
		description:
			"Connect an ESP32 physical clock that shows your active timer. Your work, displayed in the real world.",
	},
] as const;

function FloatingTimer() {
	const [seconds, setSeconds] = useState(0);

	useEffect(() => {
		const id = setInterval(() => setSeconds((s) => s + 1), 1000);
		return () => clearInterval(id);
	}, []);

	const h = String(Math.floor(seconds / 3600)).padStart(2, "0");
	const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
	const s = String(seconds % 60).padStart(2, "0");

	return (
		<div className="homepage-timer-display">
			<div className="homepage-timer-pulse" />
			<span className="homepage-timer-digits">
				{h}:{m}:{s}
			</span>
		</div>
	);
}

function FeatureCard({
	icon: Icon,
	title,
	description,
	delay = 0,
}: {
	icon: React.ComponentType<{ className?: string }>;
	title: string;
	description: string;
	delay?: number;
}) {
	return (
		<Reveal delay={delay}>
			<div className="homepage-feature-card group">
				<div className="homepage-feature-icon">
					<Icon className="w-5 h-5" />
				</div>
				<h3 className="font-heading text-lg text-foreground mb-2 tracking-tight">{title}</h3>
				<p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
			</div>
		</Reveal>
	);
}

function ShowcaseHeatmap() {
	const cells = useMemo(
		() => Array.from({ length: 52 }, () => Array.from({ length: 7 }, () => Math.random())),
		[],
	);

	return (
		<div className="flex gap-1 flex-wrap">
			{cells.map((col, i) => (
				<div key={i} className="flex flex-col gap-1">
					{col.map((intensity, j) => (
						<div
							key={j}
							className="w-2 h-2 rounded-[1px]"
							style={{
								backgroundColor:
									intensity > 0.7
										? "hsl(var(--accent) / 0.7)"
										: intensity > 0.4
											? "hsl(var(--accent) / 0.3)"
											: intensity > 0.15
												? "hsl(var(--accent) / 0.12)"
												: "hsl(var(--foreground) / 0.04)",
							}}
						/>
					))}
				</div>
			))}
		</div>
	);
}

export default function HomePage() {
	const [authOpen, setAuthOpen] = useState(false);
	const [authMode, setAuthMode] = useState<"login" | "register-email">("login");
	const hoursCounter = useCountUp(2847);
	const sessionsCounter = useCountUp(14203);
	const projectsCounter = useCountUp(312);

	const openLogin = () => {
		setAuthMode("login");
		setAuthOpen(true);
	};
	const openRegister = () => {
		setAuthMode("register-email");
		setAuthOpen(true);
	};

	return (
		<div className="homepage-root">
			<div className="homepage-ambient" />
			<div className="homepage-grid-overlay" />

			{/* Nav */}
			<nav className="homepage-nav">
				<div className="homepage-nav-inner">
					<div className="flex items-center gap-3">
						<Clock className="w-5 h-5 text-accent" />
						<span className="font-heading text-xl tracking-tight text-foreground">Beats</span>
					</div>
					<div className="flex items-center gap-3">
						<button
							className="text-sm text-muted-foreground hover:text-foreground transition-colors"
							onClick={openLogin}
						>
							Sign in
						</button>
						<Button size="sm" onClick={openRegister}>
							Get Started
						</Button>
					</div>
				</div>
			</nav>

			{/* Hero */}
			<section className="homepage-hero">
				<Reveal>
					<p className="homepage-hero-eyebrow">Time tracking, evolved</p>
				</Reveal>
				<Reveal delay={100}>
					<h1 className="homepage-hero-title">
						The most-advanced
						<br />
						<span className="homepage-hero-accent">Timer</span> app
						<br />
						for individuals
					</h1>
				</Reveal>
				<Reveal delay={200}>
					<p className="homepage-hero-subtitle">
						Track every beat of your work. Understand your rhythm.
						<br className="hidden sm:block" />
						Build better habits with deep insights into how you spend your time.
					</p>
				</Reveal>
				<Reveal delay={300}>
					<div className="flex flex-col sm:flex-row items-center gap-4 mt-10">
						<Button size="lg" onClick={openRegister} className="homepage-cta-primary">
							Start Tracking — It's Free
						</Button>
						<button
							onClick={() =>
								document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })
							}
							className="text-sm text-muted-foreground hover:text-foreground transition-colors flex items-center gap-2"
						>
							See what's inside
							<ArrowDown className="w-3.5 h-3.5 animate-bounce" />
						</button>
					</div>
				</Reveal>

				<Reveal delay={500} className="mt-16">
					<FloatingTimer />
				</Reveal>
			</section>

			{/* Stats */}
			<section className="homepage-stats-strip">
				<Reveal className="homepage-stats-inner">
					<div className="homepage-stat">
						<span className="homepage-stat-number" ref={hoursCounter.ref}>
							{hoursCounter.count.toLocaleString()}
						</span>
						<span className="homepage-stat-label">Hours Tracked</span>
					</div>
					<div className="homepage-stat-divider" />
					<div className="homepage-stat">
						<span className="homepage-stat-number" ref={sessionsCounter.ref}>
							{sessionsCounter.count.toLocaleString()}
						</span>
						<span className="homepage-stat-label">Sessions Logged</span>
					</div>
					<div className="homepage-stat-divider" />
					<div className="homepage-stat">
						<span className="homepage-stat-number" ref={projectsCounter.ref}>
							{projectsCounter.count.toLocaleString()}
						</span>
						<span className="homepage-stat-label">Projects Managed</span>
					</div>
				</Reveal>
			</section>

			{/* Features */}
			<section id="features" className="homepage-features">
				<Reveal>
					<p className="homepage-section-eyebrow">Capabilities</p>
				</Reveal>
				<Reveal delay={100}>
					<h2 className="homepage-section-title">
						Every tool you need,
						<br />
						nothing you don't
					</h2>
				</Reveal>

				<div className="homepage-features-grid">
					{FEATURES.map((f, i) => (
						<FeatureCard key={f.title} delay={i * 80} {...f} />
					))}
				</div>
			</section>

			{/* Showcase */}
			<section className="homepage-showcase">
				<Reveal>
					<div className="homepage-showcase-card">
						<div className="homepage-showcase-header">
							<div className="flex items-center gap-2">
								<div className="w-3 h-3 rounded-full bg-destructive/60" />
								<div className="w-3 h-3 rounded-full bg-accent/40" />
								<div className="w-3 h-3 rounded-full bg-success/50" />
							</div>
							<span className="text-xs text-muted-foreground font-mono">beats.app</span>
						</div>
						<div className="homepage-showcase-body">
							<div className="homepage-showcase-sidebar">
								<div className="h-3 w-16 rounded bg-accent/20 mb-6" />
								<div className="space-y-3">
									<div className="h-2.5 w-20 rounded bg-foreground/10" />
									<div className="h-2.5 w-14 rounded bg-foreground/6" />
									<div className="h-2.5 w-18 rounded bg-foreground/6" />
								</div>
								<div className="mt-8 p-3 rounded-lg bg-accent/5 border border-accent/10">
									<div className="h-2 w-8 rounded bg-accent/30 mb-2" />
									<div className="font-mono text-accent text-lg tracking-wider">01:24:07</div>
								</div>
							</div>
							<div className="homepage-showcase-main">
								<div className="h-3 w-32 rounded bg-foreground/12 mb-6" />
								<div className="grid grid-cols-3 gap-3 mb-6">
									<div className="h-16 rounded-lg bg-foreground/4 border border-foreground/6" />
									<div className="h-16 rounded-lg bg-foreground/4 border border-foreground/6" />
									<div className="h-16 rounded-lg bg-foreground/4 border border-foreground/6" />
								</div>
								<ShowcaseHeatmap />
							</div>
						</div>
					</div>
				</Reveal>
			</section>

			{/* Bottom CTA */}
			<section className="homepage-bottom-cta">
				<Reveal>
					<h2 className="homepage-section-title">
						Your time deserves
						<br />
						better than a spreadsheet
					</h2>
				</Reveal>
				<Reveal delay={100}>
					<p className="text-muted-foreground text-lg max-w-lg mx-auto mt-4">
						Free, open-source, and built for people who take their craft seriously. Passkey
						authentication — no passwords, ever.
					</p>
				</Reveal>
				<Reveal delay={200}>
					<div className="mt-10">
						<Button size="lg" onClick={openRegister} className="homepage-cta-primary">
							Get Started Now
						</Button>
					</div>
				</Reveal>
			</section>

			{/* Footer */}
			<footer className="homepage-footer">
				<div className="flex items-center gap-2 text-muted-foreground/60">
					<Clock className="w-3.5 h-3.5" />
					<span className="text-sm font-heading">Beats</span>
				</div>
				<p className="text-xs text-muted-foreground/40 mt-2">
					Built with intention. Every second counts.
				</p>
			</footer>

			<AuthModal open={authOpen} onClose={() => setAuthOpen(false)} initialMode={authMode} />
		</div>
	);
}
