import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#07080a",
        bone: "#f2efe8",
        // Each colour means one thing everywhere on the site:
        // verified = found by the deterministic engine,
        // explain  = written by the LLM layer,
        // risk     = a negative-direction / review condition.
        verified: "#6ee7c8",
        explain: "#b9a3ff",
        risk: "#ff8f70",
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
