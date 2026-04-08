/**
 * Application Configuration
 * Centralized configuration loaded from environment variables.
 */

export interface AppConfig {
	/** Base URL for the API (e.g., "http://localhost:7999") */
	apiBaseUrl: string;
	/** API token for authenticated requests */
	apiToken: string;
	/** Whether we're in development mode */
	isDev: boolean;
}

/**
 * Application configuration singleton
 */
export const config: AppConfig = {
	apiBaseUrl: import.meta.env.VITE_API_URL || "http://localhost:7999",
	apiToken: import.meta.env.VITE_API_TOKEN || "",
	isDev: import.meta.env.DEV,
};
