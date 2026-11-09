import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Theme-aware: each colour reads an RGB channel triple from globals.css, so the light
        // theme flips every overlay (bg-white/5, border-white/15, ...) without touching components.
        // "white" is the foreground ink and "black" the page colour in whichever theme is active.
        white: "rgb(var(--fg-rgb) / <alpha-value>)",
        black: "rgb(var(--bg-rgb) / <alpha-value>)",
        ink: "rgb(var(--bg-rgb) / <alpha-value>)",
        bone: "rgb(var(--bone-rgb) / <alpha-value>)",
        raised: "rgb(var(--raised-rgb) / <alpha-value>)",
        // Each colour means one thing everywhere on the site:
        // verified = found by the deterministic engine,
        // explain  = written by the LLM layer,
        // risk     = a negative-direction / review condition.
        verified: "rgb(var(--verified-rgb) / <alpha-value>)",
        explain: "rgb(var(--explain-rgb) / <alpha-value>)",
        risk: "rgb(var(--risk-rgb) / <alpha-value>)",
        caution: "rgb(var(--caution-rgb) / <alpha-value>)",
        mild: "rgb(var(--mild-rgb) / <alpha-value>)",
        severe: "rgb(var(--severe-rgb) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-inter)", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      maxWidth: { page: "76rem" },
    },
  },
  plugins: [],
};

export default config;
