/**
 * Tailwind CSS class name utility
 */
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes with proper precedence
 */
export function cn(...inputs: ClassValue[]): string {
	return twMerge(clsx(inputs));
}
