/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        // Semantic design tokens mirrored from SmarterVote's web/tailwind.config.js —
        // keep these two files in sync if the brand palette changes.
        page: "rgb(var(--sv-page) / <alpha-value>)",
        surface: "rgb(var(--sv-surface) / <alpha-value>)",
        "surface-alt": "rgb(var(--sv-surface-alt) / <alpha-value>)",
        stroke: "rgb(var(--sv-border) / <alpha-value>)",
        content: {
          DEFAULT: "rgb(var(--sv-text) / <alpha-value>)",
          muted: "rgb(var(--sv-text-muted) / <alpha-value>)",
          subtle: "rgb(var(--sv-text-subtle) / <alpha-value>)",
          faint: "rgb(var(--sv-text-faint) / <alpha-value>)",
        },
        primary: {
          50: "#eff6ff",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
      },
    },
  },
  plugins: [],
};
