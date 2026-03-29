import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{html,js,svelte,ts}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        // Semantic design tokens — switch between light/dark via CSS variables
        page:    "rgb(var(--sv-page) / <alpha-value>)",
        surface: "rgb(var(--sv-surface) / <alpha-value>)",
        "surface-alt": "rgb(var(--sv-surface-alt) / <alpha-value>)",
        stroke:  "rgb(var(--sv-border) / <alpha-value>)",
        content: {
          DEFAULT: "rgb(var(--sv-text) / <alpha-value>)",
          muted:   "rgb(var(--sv-text-muted) / <alpha-value>)",
          subtle:  "rgb(var(--sv-text-subtle) / <alpha-value>)",
          faint:   "rgb(var(--sv-text-faint) / <alpha-value>)",
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
  plugins: [typography],
};
