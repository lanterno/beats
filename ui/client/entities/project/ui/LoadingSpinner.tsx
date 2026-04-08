/**
 * Loading Spinner Component
 * Full-page loading indicator.
 */

interface LoadingSpinnerProps {
	message?: string;
}

export function LoadingSpinner({ message = "Loading..." }: LoadingSpinnerProps) {
	return (
		<div className="min-h-screen bg-background flex items-center justify-center">
			<div className="text-center">
				<div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto mb-4" />
				<p className="text-muted-foreground text-base">{message}</p>
			</div>
		</div>
	);
}
