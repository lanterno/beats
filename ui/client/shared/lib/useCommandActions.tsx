/**
 * Builds the full set of commands available to the command palette.
 *
 * Pulls timer / theme / auth state in one place so the palette stays a dumb
 * presentational component. Exposes `recencyBoost` and `recordInvocation` so
 * frequently-invoked commands float to the top of the list.
 */

import {
	ArrowRight,
	BarChart3,
	CalendarCheck,
	Clock,
	FileBarChart2,
	LogOut,
	Moon,
	Palette,
	Settings as SettingsIcon,
	Sun,
} from "lucide-react";
import { useCallback, useMemo } from "react";
import { type NavigateFunction, useNavigate } from "react-router-dom";
import { clearSessionToken, logout } from "@/features/auth";
import type { CommandItem } from "@/shared/ui";
import {
	type ColorMode,
	DENSITIES,
	type Density,
	THEMES,
	type ThemeName,
	useTheme,
} from "./useTheme";

const RECENCY_KEY = "beats_command_recency";
const RECENCY_MAX = 20;
const BOOST_PER_HIT = 0.08;
const BOOST_CAP = 0.4;

export interface CommandContext {
	projects: Array<{ id: string; name: string; color: string }>;
	isTimerRunning: boolean;
	onToggleTimer: () => void;
}

type RecencyMap = Record<string, number>;

function readRecency(): RecencyMap {
	try {
		const raw = localStorage.getItem(RECENCY_KEY);
		if (!raw) return {};
		const parsed = JSON.parse(raw);
		return typeof parsed === "object" && parsed !== null ? (parsed as RecencyMap) : {};
	} catch {
		return {};
	}
}

function writeRecency(map: RecencyMap) {
	try {
		localStorage.setItem(RECENCY_KEY, JSON.stringify(map));
	} catch {
		// ignore storage failures
	}
}

export function useCommandActions(ctx: CommandContext): {
	items: CommandItem[];
	recencyBoost: (id: string) => number;
	recordInvocation: (id: string) => void;
} {
	const navigate = useNavigate();
	const { theme, setTheme, mode, setMode, density, setDensity } = useTheme();

	const items = useMemo<CommandItem[]>(
		() => buildItems(ctx, navigate, theme, setTheme, mode, setMode, density, setDensity),
		[ctx, navigate, theme, setTheme, mode, setMode, density, setDensity],
	);

	const recencyBoost = useCallback((id: string) => {
		const hits = readRecency()[id] ?? 0;
		return Math.min(BOOST_CAP, hits * BOOST_PER_HIT);
	}, []);

	const recordInvocation = useCallback((id: string) => {
		const map = readRecency();
		map[id] = (map[id] ?? 0) + 1;

		// Cap size so the map doesn't grow forever; drop least-frequent entries.
		const keys = Object.keys(map);
		if (keys.length > RECENCY_MAX) {
			const sorted = keys.sort((a, b) => map[b] - map[a]).slice(0, RECENCY_MAX);
			const trimmed: RecencyMap = {};
			for (const k of sorted) trimmed[k] = map[k];
			writeRecency(trimmed);
		} else {
			writeRecency(map);
		}
	}, []);

	return { items, recencyBoost, recordInvocation };
}

function buildItems(
	ctx: CommandContext,
	navigate: NavigateFunction,
	theme: ThemeName,
	setTheme: (t: ThemeName) => void,
	mode: ColorMode,
	setMode: (m: ColorMode) => void,
	density: Density,
	setDensity: (d: Density) => void,
): CommandItem[] {
	const items: CommandItem[] = [];

	// Timer
	items.push({
		id: "timer.toggle",
		label: ctx.isTimerRunning ? "Stop timer" : "Start timer",
		keywords: ["beat", "pomodoro", "session"],
		sublabel: "Space",
		icon: <Clock className="w-4 h-4" />,
		action: ctx.onToggleTimer,
	});

	// Navigation
	const nav: Array<[string, string, string, React.ReactNode, string[]]> = [
		[
			"nav.dashboard",
			"Go to Dashboard",
			"/app",
			<ArrowRight key="d" className="w-4 h-4" />,
			["home", "today"],
		],
		[
			"nav.insights",
			"Go to Insights",
			"/insights",
			<BarChart3 key="i" className="w-4 h-4" />,
			["analytics", "heatmap", "charts"],
		],
		[
			"nav.digests",
			"Go to Weekly Digests",
			"/insights/digests",
			<FileBarChart2 key="g" className="w-4 h-4" />,
			["digest", "weekly", "summary"],
		],
		[
			"nav.plan",
			"Go to Planning",
			"/plan",
			<CalendarCheck key="p" className="w-4 h-4" />,
			["intentions", "week", "plan"],
		],
		[
			"nav.settings",
			"Go to Settings",
			"/settings",
			<SettingsIcon key="s" className="w-4 h-4" />,
			["config", "preferences"],
		],
	];
	for (const [id, label, path, icon, keywords] of nav) {
		items.push({
			id,
			label,
			sublabel: path,
			icon,
			keywords,
			action: () => navigate(path),
		});
	}

	// Projects
	ctx.projects.forEach((p, i) => {
		items.push({
			id: `project.${p.id}`,
			label: p.name,
			sublabel: i < 9 ? `${i + 1}` : undefined,
			color: p.color,
			keywords: ["project", "open"],
			action: () => navigate(`/project/${p.id}`),
		});
	});

	// Theme cycle
	items.push({
		id: "theme.cycle",
		label: `Theme: ${THEMES.find((t) => t.id === theme)?.label ?? theme} (cycle)`,
		keywords: ["color", "palette", "dark", ...THEMES.map((t) => t.label.toLowerCase())],
		icon: <Palette className="w-4 h-4" />,
		action: () => {
			const order = THEMES.map((t) => t.id);
			const next = order[(order.indexOf(theme) + 1) % order.length];
			setTheme(next);
		},
	});

	// Mode toggle
	items.push({
		id: "mode.toggle",
		label: `Mode: ${mode === "dark" ? "Dark" : "Light"} (toggle)`,
		keywords: ["dark", "light", "mode", "brightness"],
		icon: mode === "dark" ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />,
		action: () => setMode(mode === "dark" ? "light" : "dark"),
	});

	// Density cycle
	items.push({
		id: "density.cycle",
		label: `Density: ${DENSITIES.find((d) => d.id === density)?.label ?? density} (cycle)`,
		keywords: ["compact", "comfortable", "spacious", "spacing"],
		icon: <Moon className="w-4 h-4" />,
		action: () => {
			const order = DENSITIES.map((d) => d.id);
			const next = order[(order.indexOf(density) + 1) % order.length];
			setDensity(next);
		},
	});

	// Sign out
	items.push({
		id: "auth.logout",
		label: "Sign out",
		keywords: ["logout", "signout", "exit"],
		icon: <LogOut className="w-4 h-4" />,
		action: () => {
			logout()
				.catch(() => {})
				.finally(() => {
					clearSessionToken();
					window.location.replace("/");
				});
		},
	});

	return items;
}
