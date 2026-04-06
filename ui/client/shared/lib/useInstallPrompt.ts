/**
 * PWA Install Prompt Hook
 * Captures the beforeinstallprompt event and exposes install trigger.
 * Dismissal preference persisted in localStorage.
 */
import { useState, useEffect, useCallback } from "react";

const DISMISSED_KEY = "beats_install_dismissed";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function useInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(() =>
    localStorage.getItem(DISMISSED_KEY) === "true"
  );

  useEffect(() => {
    function handler(e: Event) {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    }
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  const install = useCallback(async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      setDeferredPrompt(null);
    }
  }, [deferredPrompt]);

  const dismiss = useCallback(() => {
    setDismissed(true);
    localStorage.setItem(DISMISSED_KEY, "true");
    setDeferredPrompt(null);
  }, []);

  const canShow = !!deferredPrompt && !dismissed;

  return { canShow, install, dismiss };
}
