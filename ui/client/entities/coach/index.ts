/**
 * Coach entity — public API
 */
export type { BriefResponse, ChatSSEEvent, UsageSummaryResponse } from "./api";
export {
	coachKeys,
	fetchChatHistory,
	useCoachBrief,
	useCoachBriefHistory,
	useCoachUsage,
	useGenerateBrief,
} from "./api";
export { type ChatMessage, useCoachChat } from "./useCoachChat";
