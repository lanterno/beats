/**
 * Intelligence API layer - public API
 */

// Low-level API functions
export {
	fetchProductivityScore,
	fetchSuggestions,
	generateDigest,
} from "./intelligenceApi";
// TanStack Query hooks
export {
	intelligenceKeys,
	useDigests,
	useDismissInboxItem,
	useDismissPattern,
	useFocusScores,
	useGenerateDigest,
	useInbox,
	usePatterns,
	useProductivityScore,
	useProjectHealth,
	useRefreshPatterns,
	useScoreHistory,
	useSuggestions,
} from "./queries";
