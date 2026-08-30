/**
 * Light/dark theming.
 *
 * The choice is NOT persisted. Browser storage is banned in this app (SI-24),
 * and a session that resets with the process matches how the backend treats
 * sessions: memory only. On load we follow the operating system.
 *
 * HeroUI v3 reads both the class and the `data-theme` attribute, so both are
 * set together.
 */

export type Theme = "light" | "dark";

export function detectSystemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.remove("light", "dark");
  root.classList.add(theme);
  root.dataset["theme"] = theme;
  root.style.colorScheme = theme;
}
