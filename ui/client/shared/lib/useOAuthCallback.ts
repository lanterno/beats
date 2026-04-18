import { useEffect, useRef } from "react";

/**
 * Handle OAuth redirect callback by checking URL params and invoking the connect mutation.
 * Cleans up the URL after processing.
 */
export function useOAuthCallback(
	paramName: string,
	connectFn: (code: string, opts: { onSuccess: () => void; onError: () => void }) => void,
	onSuccess: () => void,
	onError: () => void,
) {
	const onSuccessRef = useRef(onSuccess);
	const onErrorRef = useRef(onError);
	onSuccessRef.current = onSuccess;
	onErrorRef.current = onError;

	useEffect(() => {
		const params = new URLSearchParams(window.location.search);
		if (params.get(paramName) === "callback" && params.get("code")) {
			const code = params.get("code")!;
			connectFn(code, {
				onSuccess: () => onSuccessRef.current(),
				onError: () => onErrorRef.current(),
			});
			window.history.replaceState({}, "", window.location.pathname);
		}
	}, [paramName, connectFn]);
}
