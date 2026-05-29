/**
 * Intelligence entity - public API
 */

export {
	intelligenceKeys,
	useDigests,
	useDismissInboxItem,
	useDismissPattern,
	useEstimationAccuracy,
	useFocusScores,
	useGenerateDigest,
	useInbox,
	useMoodCorrelation,
	usePatterns,
	useProductivityScore,
	useProjectHealth,
	useRefreshPatterns,
	useScoreHistory,
	useSuggestions,
} from "./api";
export type { InboxItem, InboxResponse } from "./api/intelligenceApi";
