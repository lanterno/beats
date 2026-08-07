/**
 * App Error Boundary
 * Catches render/runtime errors anywhere in the tree and shows a recovery
 * screen instead of unmounting to a blank (dark) page. Without this, a single
 * throw during render leaves an empty root over the dark body background —
 * i.e. "everything turns black".
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
	children: ReactNode;
}

interface State {
	error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
	state: State = { error: null };

	static getDerivedStateFromError(error: Error): State {
		return { error };
	}

	componentDidCatch(error: Error, info: ErrorInfo) {
		// Surface the failure for debugging (visible in mobile remote consoles too).
		console.error("Uncaught render error:", error, info.componentStack);
	}

	render() {
		if (!this.state.error) return this.props.children;

		return (
			<div className="min-h-screen bg-background flex items-center justify-center p-6">
				<div className="max-w-sm w-full text-center space-y-4">
					<h1 className="text-lg font-heading font-semibold text-foreground">
						Something went wrong
					</h1>
					<p className="text-sm text-muted-foreground">
						The app hit an unexpected error and couldn't finish loading this view.
					</p>
					<button
						type="button"
						onClick={() => {
							this.setState({ error: null });
							window.location.reload();
						}}
						className="inline-flex items-center justify-center rounded-md bg-accent text-accent-foreground px-4 py-2 text-sm font-medium hover:bg-accent/85 transition-colors"
					>
						Reload
					</button>
				</div>
			</div>
		);
	}
}
