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
	useDismissPattern,
	useEstimationAccuracy,
	useFocusScores,
	useGenerateDigest,
	useMoodCorrelation,
	usePatterns,
	useProductivityScore,
	useProjectHealth,
	useRefreshPatterns,
	useScoreHistory,
	useSuggestions,
} from "./queries";
