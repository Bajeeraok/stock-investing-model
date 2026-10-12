import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#f0fdf4",
          100: "#dcfce7",
          500: "#22c55e",
          600: "#16a34a",
          700: "#15803d",
        },
        surface: {
          dark: "#0f172a",
          card: "#1e293b",
          hover: "#334155",
        },
        /** Fintech semantic palette — desaturated, easy on eyes during long sessions */
        fintech: {
          green:  "#00C896",   // matte emerald — confirmed trades, bull
          red:    "#FF6B6B",   // soft muted red — stops, bear
          amber:  "#F59E0B",   // transition / caution
          cyan:   "#22D3EE",   // anchor / MOS reference
          violet: "#A78BFA",   // long-term tiers
        },
        /** Ticker-detail skin — scoped to `.td-skin` (see globals.css), not used elsewhere
         * in the app. rgb()+CSS-var pattern keeps opacity modifiers (bg-td-accent/10) working.
         * Neutrals (ink/bg/surface/surface2/line/text/muted) come from the Thrive Alpha
         * Redesign artifact's layered dark palette — the thing actually missing from today's
         * flat slate-900/800 chrome. Semantic accents (accent/warn/crit/owner/info) map to
         * this app's EXISTING `fintech.*` palette above instead of the artifact's own hues —
         * that palette was already a deliberate, validated "desaturated, easy on eyes during
         * long sessions" choice and shouldn't be thrown out for a mockup's colors. */
        td: {
          ink:         "rgb(var(--td-ink) / <alpha-value>)",
          bg:          "rgb(var(--td-bg) / <alpha-value>)",
          surface:     "rgb(var(--td-surface) / <alpha-value>)",
          surface2:    "rgb(var(--td-surface2) / <alpha-value>)",
          line:        "rgb(var(--td-line) / <alpha-value>)",
          text:        "rgb(var(--td-text) / <alpha-value>)",
          muted:       "rgb(var(--td-muted) / <alpha-value>)",
          accent:      "rgb(var(--td-accent) / <alpha-value>)",        // = fintech.green
          "accent-ink":  "rgb(var(--td-accent-ink) / <alpha-value>)",
          "accent-weak": "rgb(var(--td-accent-weak) / <alpha-value>)",
          warn:        "rgb(var(--td-warn) / <alpha-value>)",          // = fintech.amber
          "warn-weak":   "rgb(var(--td-warn-weak) / <alpha-value>)",
          crit:        "rgb(var(--td-crit) / <alpha-value>)",          // = fintech.red
          "crit-weak":   "rgb(var(--td-crit-weak) / <alpha-value>)",
          owner:       "rgb(var(--td-owner) / <alpha-value>)",         // = fintech.violet
          "owner-weak":  "rgb(var(--td-owner-weak) / <alpha-value>)",
          info:        "rgb(var(--td-info) / <alpha-value>)",         // = fintech.cyan
        },
      },
      fontFamily: {
        sans: ["system-ui", "sans-serif"],
        /** JetBrains Mono → ui-monospace fallback for all price figures */
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
        /** Ticker-detail skin's UI typeface — scoped via `font-td-sans`, not the app-wide
         * `sans` key above. Numeric text inside the skin keeps using the existing `font-mono`
         * (JetBrains Mono) — no second mono face is introduced. */
        "td-sans": ["var(--font-td-sans)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
