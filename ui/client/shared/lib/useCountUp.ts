import { useEffect, useRef, useState } from "react";

export function useCountUp(target: number, duration = 2000) {
	const [count, setCount] = useState(0);
	const ref = useRef<HTMLSpanElement>(null);
	const started = useRef(false);

	useEffect(() => {
		if (!ref.current) return;
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
	}, [target, duration]);

	return { count, ref };
}
