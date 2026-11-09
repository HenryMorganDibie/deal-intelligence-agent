"use client";

import { useEffect, useState } from "react";
import { THEME_COLOR, THEME_KEY, type Theme } from "../lib/theme";

function apply(theme: Theme) {
  const root = document.documentElement;
  if (theme === "light") root.dataset.theme = "light";
  else delete root.dataset.theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode: the choice lasts for this page only */ }
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  // Unknown until mounted: the server cannot see the reader's stored choice.
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
    const onStorage = (e: StorageEvent) => {
      if (e.key !== THEME_KEY) return;
      const next: Theme = e.newValue === "light" ? "light" : "dark";
      apply(next);
      setTheme(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const next: Theme = theme === "light" ? "dark" : "light";
  return (
    <button
      type="button"
      className={`btn btn-ghost h-9 w-9 shrink-0 p-0 ${className}`}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      onClick={() => { apply(next); setTheme(next); }}
    >
      <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
        {theme === "light" ? (
          // Moon: offered while the page is light.
          <path d="M13.5 9.6A5.5 5.5 0 0 1 6.4 2.5a5.5 5.5 0 1 0 7.1 7.1Z" strokeLinejoin="round" />
        ) : (
          // Sun: offered while the page is dark (and before mount).
          <>
            <circle cx="8" cy="8" r="2.8" />
            <path d="M8 1.5v1.3M8 13.2v1.3M1.5 8h1.3M13.2 8h1.3M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9" />
          </>
        )}
      </svg>
    </button>
  );
}
