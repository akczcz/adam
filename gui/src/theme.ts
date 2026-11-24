// Motiv GUI (brief: dark výchozí i bez preference, light přepínatelný, volba v localStorage). Atribut data-theme na <html> čte tokens.css.
export type Theme = "dark" | "light";
const KEY = "gui_theme";

export function readStoredTheme(): Theme | null {
  try { const v = localStorage.getItem(KEY); return v === "light" || v === "dark" ? v : null; } catch { return null; }
}
export function systemTheme(): Theme {
  try { return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark"; } catch { return "dark"; }
}
export function currentTheme(): Theme { return (document.documentElement.getAttribute("data-theme") as Theme | null) ?? readStoredTheme() ?? systemTheme(); }

export function applyTheme(t: Theme, persist = true) {
  document.documentElement.setAttribute("data-theme", t);
  if (persist) { try { localStorage.setItem(KEY, t); } catch { /* soukromé okno */ } }
}
/** Při startu: uložená volba > systémová preference > dark. Bez uložené volby sleduje změnu systémové preference. */
export function initTheme() {
  applyTheme(readStoredTheme() ?? systemTheme(), false);
  try {
    window.matchMedia?.("(prefers-color-scheme: light)").addEventListener?.("change", () => { if (!readStoredTheme()) applyTheme(systemTheme(), false); });
  } catch { /* bez matchMedia */ }
}
export function toggleTheme(): Theme { const t: Theme = currentTheme() === "dark" ? "light" : "dark"; applyTheme(t); return t; }
