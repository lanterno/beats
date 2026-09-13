/**
 * The painting behind the app: a sky gradient, the sun, five drifting clouds
 * and three hills at the foot of the screen. Viewport-fixed, under everything,
 * and invisible to assistive tech. The styles are the `.sky` block in
 * global.css; the colours are the theme's `--sky-*`, `--cloud*` and `--hill-*`
 * tokens, so the same markup is the afternoon and the dusk.
 */
export function SkyBackdrop() {
	return (
		<div className="sky" aria-hidden="true">
			<div className="sun" />
			<div className="cloud cloud-1" />
			<div className="cloud cloud-2" />
			<div className="cloud cloud-3" />
			<div className="cloud cloud-4" />
			<div className="cloud cloud-5" />
			<svg className="hills" viewBox="0 0 1440 200" preserveAspectRatio="none" aria-hidden="true">
				<path
					className="far"
					d="M0 118 C 160 70, 330 96, 520 84 S 860 40, 1060 86 S 1340 108, 1440 92 L1440 200 L0 200 Z"
				/>
				<path
					className="mid"
					d="M0 146 C 200 104, 380 150, 600 124 S 920 92, 1120 134 S 1360 156, 1440 132 L1440 200 L0 200 Z"
				/>
				<path
					className="near"
					d="M0 172 C 240 140, 440 184, 720 158 S 1080 128, 1300 168 S 1400 176, 1440 166 L1440 200 L0 200 Z"
				/>
			</svg>
		</div>
	);
}
