// Light/dark theme: default follows the OS, a manual choice overrides and persists.
// The active theme is applied to <html data-theme>; tokens swap via CSS variables.
export type ThemeChoice = "auto" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const KEY = "sirina-theme";

declare global {
  interface Window {
    __THEME__?: string;
    __BACKEND_URL__?: string;
  }
}

function isChoice(v: unknown): v is ThemeChoice {
  return v === "light" || v === "dark" || v === "auto";
}

export function getThemeChoice(): ThemeChoice {
  // The backend-injected value wins (durable across the packaged app's per-launch port,
  // which wipes localStorage); localStorage is a same-session cache / dev fallback.
  if (typeof window !== "undefined" && isChoice(window.__THEME__)) return window.__THEME__;
  try {
    const v = localStorage.getItem(KEY);
    if (isChoice(v)) return v;
  } catch {
    /* ignore */
  }
  return "auto";
}

function osPrefersDark(): boolean {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches;
}

export function resolveTheme(choice: ThemeChoice = getThemeChoice()): ResolvedTheme {
  return choice === "auto" ? (osPrefersDark() ? "dark" : "light") : choice;
}

export function applyTheme(choice: ThemeChoice = getThemeChoice()): void {
  document.documentElement.setAttribute("data-theme", resolveTheme(choice));
}

const listeners = new Set<() => void>();
function notify() {
  for (const l of listeners) l();
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function setThemeChoice(choice: ThemeChoice): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    /* ignore */
  }
  if (typeof window !== "undefined") window.__THEME__ = choice;
  // Durably persist server-side (best-effort; localStorage above covers the offline case).
  try {
    const base = (typeof window !== "undefined" && window.__BACKEND_URL__) || "";
    void fetch(base + "/api/ui/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: choice }),
    }).catch(() => {});
  } catch {
    /* ignore */
  }
  applyTheme(choice);
  notify();
}

// Follow OS changes while in auto mode.
if (typeof matchMedia !== "undefined") {
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
    if (getThemeChoice() === "auto") {
      applyTheme();
      notify();
    }
  });
}

// Apply on import (a redundant safety net; index.html also sets it pre-paint).
applyTheme();
