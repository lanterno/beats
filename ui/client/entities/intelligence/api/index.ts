// Low-level API functions
export {
	fetchProductivityScore,
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
} from "./queries";
