/**
 * Application Configuration
 * Centralized configuration loaded from environment variables.
 */

export interface AppConfig {
	/** Base URL for the API (e.g., "http://localhost:7999") */
	apiBaseUrl: string;
	/** Whether we're in development mode */
	isDev: boolean;
}

/**
 * Application configuration singleton
 */
export const config: AppConfig = {
	apiBaseUrl: import.meta.env.VITE_API_URL || "http://localhost:7999",
	isDev: import.meta.env.DEV,
};
