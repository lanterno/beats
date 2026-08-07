/**
 * Intelligence entity - public API
 */

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
} from "./api";
export type { InboxItem, InboxResponse } from "./api/intelligenceApi";
