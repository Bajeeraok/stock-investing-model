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
      },
      fontFamily: {
        sans: ["system-ui", "sans-serif"],
        /** JetBrains Mono → ui-monospace fallback for all price figures */
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
