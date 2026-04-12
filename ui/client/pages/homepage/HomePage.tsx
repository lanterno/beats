/**
 * Public Homepage / Landing Page
 * Shown to unauthenticated visitors. Premium, editorial aesthetic.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/shared/ui";

/* ─── Animated counter hook ─── */
function useCountUp(target: number, duration = 2000, startOnView = true) {
	const [count, setCount] = useState(0);
	const ref = useRef<HTMLSpanElement>(null);
	const started = useRef(false);

	useEffect(() => {
		if (!startOnView || !ref.current) return;
		const observer = new IntersectionObserver(
			([entry]) => {
				if (entry.isIntersecting && !started.current) {
					started.current = true;
					const start = performance.now();
					const animate = (now: number) => {
						const elapsed = now - start;
						const progress = Math.min(elapsed / duration, 1);
						const eased = 1 - (1 - progress) ** 3;
						setCount(Math.round(eased * target));
						if (progress < 1) requestAnimationFrame(animate);
					};
					requestAnimationFrame(animate);
				}
			},
			{ threshold: 0.5 },
		);
		observer.observe(ref.current);
		return () => observer.disconnect();
	}, [target, duration, startOnView]);

	return { count, ref };
}

/* ─── Fade-in-on-scroll wrapper ─── */
function Reveal({
	children,
	className = "",
	delay = 0,
}: { children: React.ReactNode; className?: string; delay?: number }) {
	const ref = useRef<HTMLDivElement>(null);
	const [visible, setVisible] = useState(false);

	useEffect(() => {
		if (!ref.current) return;
		const observer = new IntersectionObserver(
			([entry]) => {
				if (entry.isIntersecting) {
					setVisible(true);
					observer.disconnect();
				}
			},
			{ threshold: 0.15 },
		);
		observer.observe(ref.current);
		return () => observer.disconnect();
	}, []);

	return (
		<div
			ref={ref}
			className={className}
			style={{
				opacity: visible ? 1 : 0,
				transform: visible ? "translateY(0)" : "translateY(24px)",
				transition: `opacity 0.7s cubic-bezier(0.16,1,0.3,1) ${delay}ms, transform 0.7s cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
			}}
		>
			{children}
		</div>
	);
}

/* ─── Floating timer display (hero accent) ─── */
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

/* ─── Feature card ─── */
function FeatureCard({
	icon,
	title,
	description,
	delay = 0,
}: { icon: React.ReactNode; title: string; description: string; delay?: number }) {
	return (
		<Reveal delay={delay}>
			<div className="homepage-feature-card group">
				<div className="homepage-feature-icon">{icon}</div>
				<h3 className="font-heading text-lg text-foreground mb-2 tracking-tight">{title}</h3>
				<p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
			</div>
		</Reveal>
	);
}

/* ─── Main Homepage ─── */
export default function HomePage() {
	const navigate = useNavigate();
	const hoursCounter = useCountUp(2847);
	const sessionsCounter = useCountUp(14203);
	const projectsCounter = useCountUp(312);

	return (
		<div className="homepage-root">
			{/* ── Ambient background ── */}
			<div className="homepage-ambient" />
			<div className="homepage-grid-overlay" />

			{/* ── Navigation ── */}
			<nav className="homepage-nav">
				<div className="homepage-nav-inner">
					<div className="flex items-center gap-3">
						<div className="homepage-logo-mark">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
								<circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
								<path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
							</svg>
						</div>
						<span className="font-heading text-xl tracking-tight text-foreground">Beats</span>
					</div>
					<div className="flex items-center gap-3">
						<button
							className="text-sm text-muted-foreground hover:text-foreground transition-colors"
							onClick={() => navigate("/login")}
						>
							Sign in
						</button>
						<Button size="sm" onClick={() => navigate("/login")}>
							Get Started
						</Button>
					</div>
				</div>
			</nav>

			{/* ── Hero ── */}
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
						<Button size="lg" onClick={() => navigate("/login")} className="homepage-cta-primary">
							Start Tracking — It's Free
						</Button>
						<button
							onClick={() => {
								document.getElementById("features")?.scrollIntoView({ behavior: "smooth" });
							}}
							className="text-sm text-muted-foreground hover:text-foreground transition-colors flex items-center gap-2"
						>
							See what's inside
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="animate-bounce">
								<path
									d="M12 5v14m0 0l-6-6m6 6l6-6"
									stroke="currentColor"
									strokeWidth="2"
									strokeLinecap="round"
									strokeLinejoin="round"
								/>
							</svg>
						</button>
					</div>
				</Reveal>

				{/* Floating timer accent */}
				<Reveal delay={500} className="mt-16">
					<FloatingTimer />
				</Reveal>
			</section>

			{/* ── Social proof strip ── */}
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

			{/* ── Features ── */}
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
					<FeatureCard
						delay={0}
						icon={
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
								<rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
								<rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
								<rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
								<rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
							</svg>
						}
						title="Project-Based Tracking"
						description="Organize time by project with color-coded categories. Set weekly goals as targets or caps — stay focused on what matters."
					/>
					<FeatureCard
						delay={80}
						icon={
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
								<path d="M3 3v18h18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
								<path d="M7 16l4-6 4 3 5-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
							</svg>
						}
						title="Daily Rhythm Insights"
						description="Visualize when you're most productive. Discover your natural patterns with hour-by-hour activity breakdowns."
					/>
					<FeatureCard
						delay={160}
						icon={
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
								<circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
								<path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
							</svg>
						}
						title="Weekly Goals"
						description="Set time targets for each project. Track progress with visual goal rings that update in real-time as you work."
					/>
					<FeatureCard
						delay={240}
						icon={
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
								<rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" />
								<path d="M3 10h18" stroke="currentColor" strokeWidth="1.5" />
								<path d="M9 4v16" stroke="currentColor" strokeWidth="1.5" />
							</svg>
						}
						title="Contribution Heatmap"
						description="GitHub-style heatmap of your work year. See streaks, gaps, and long-term consistency at a glance."
					/>
					<FeatureCard
						delay={320}
						icon={
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
								<circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
								<path d="M12 14c-4.5 0-8 2-8 4.5V20h16v-1.5c0-2.5-3.5-4.5-8-4.5z" stroke="currentColor" strokeWidth="1.5" />
							</svg>
						}
						title="Mood & Energy Tracking"
						description="Log how you feel at end-of-day. Correlate mood with productivity to understand what drives your best work."
					/>
					<FeatureCard
						delay={400}
						icon={
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
								<rect x="2" y="6" width="20" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
								<circle cx="12" cy="12" r="2" fill="currentColor" />
								<path d="M7 6V4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
								<path d="M17 6V4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
							</svg>
						}
						title="Wall Clock Sync"
						description="Connect an ESP32 physical clock that shows your active timer. Your work, displayed in the real world."
					/>
				</div>
			</section>

			{/* ── Showcase / App Preview ── */}
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
							{/* Fake sidebar */}
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
							{/* Fake main content */}
							<div className="homepage-showcase-main">
								<div className="h-3 w-32 rounded bg-foreground/12 mb-6" />
								<div className="grid grid-cols-3 gap-3 mb-6">
									<div className="h-16 rounded-lg bg-foreground/4 border border-foreground/6" />
									<div className="h-16 rounded-lg bg-foreground/4 border border-foreground/6" />
									<div className="h-16 rounded-lg bg-foreground/4 border border-foreground/6" />
								</div>
								{/* Fake heatmap */}
								<div className="flex gap-1 flex-wrap">
									{Array.from({ length: 52 }, (_, i) => (
										<div key={i} className="flex flex-col gap-1">
											{Array.from({ length: 7 }, (_, j) => {
												const intensity = Math.random();
												return (
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
												);
											})}
										</div>
									))}
								</div>
							</div>
						</div>
					</div>
				</Reveal>
			</section>

			{/* ── Bottom CTA ── */}
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
						Free, open-source, and built for people who take their craft seriously.
						Passkey authentication — no passwords, ever.
					</p>
				</Reveal>
				<Reveal delay={200}>
					<div className="mt-10">
						<Button size="lg" onClick={() => navigate("/login")} className="homepage-cta-primary">
							Get Started Now
						</Button>
					</div>
				</Reveal>
			</section>

			{/* ── Footer ── */}
			<footer className="homepage-footer">
				<div className="flex items-center gap-2 text-muted-foreground/60">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none">
						<circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
						<path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
					</svg>
					<span className="text-sm font-heading">Beats</span>
				</div>
				<p className="text-xs text-muted-foreground/40 mt-2">
					Built with intention. Every second counts.
				</p>
			</footer>
		</div>
	);
}
