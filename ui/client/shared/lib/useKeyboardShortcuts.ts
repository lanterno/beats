/**
 * Keyboard Shortcuts Hook
 * Handles global keyboard shortcuts for timer control and navigation.
 */
import { useEffect } from "react";

interface ShortcutActions {
  toggleTimer: () => void;
  selectProject: (index: number) => void;
  openCommandPalette: () => void;
}

function isInputFocused(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    (el as HTMLElement).isContentEditable
  );
}

export function useKeyboardShortcuts(actions: ShortcutActions) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Cmd+K or Ctrl+K — command palette
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        actions.openCommandPalette();
        return;
      }

      // Skip shortcuts when typing in inputs
      if (isInputFocused()) return;

      // "/" — command palette (not in input)
      if (e.key === "/") {
        e.preventDefault();
        actions.openCommandPalette();
        return;
      }

      // Space — toggle timer
      if (e.key === " " || e.code === "Space") {
        e.preventDefault();
        actions.toggleTimer();
        return;
      }

      // 1-9 — select project by index
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9) {
        e.preventDefault();
        actions.selectProject(num - 1);
        return;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [actions]);
}
