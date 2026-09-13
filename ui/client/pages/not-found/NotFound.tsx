/**
 * Not Found Page
 * 404 error page.
 */

import { Link } from "react-router";
import { Button } from "@/shared/ui";

export default function NotFound() {
	return (
		<div className="min-h-screen bg-background flex items-center justify-center">
			<div className="text-center px-6">
				<p className="font-heading text-7xl font-extrabold tracking-[-0.035em] text-muted-foreground">
					404
				</p>
				<p className="mt-4 text-base font-medium text-foreground">This page does not exist.</p>
				{/* The page's one action, so the accent pill. */}
				<Button asChild className="mt-8">
					<Link to="/app">Return home</Link>
				</Button>
			</div>
		</div>
	);
}
