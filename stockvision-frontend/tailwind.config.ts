import type { Config } from "tailwindcss";

/**
 * Design tokens.
 *
 * Every colour is declared as an HSL channel triplet in globals.css and
 * referenced here through `hsl(var(--token) / <alpha-value>)`. That indirection
 * is what makes `bg-surface/60` (a translucent glass panel) work with the same
 * token `bg-surface` uses — a hex literal cannot take an alpha modifier, which is
 * why the v1 palette had to hardcode rgba() values inside component files.
 *
 * The palette is a near-black slate with an electric-blue primary and a violet
 * secondary. Gain/loss greens and reds are reserved EXCLUSIVELY for P&L and
 * directional signals — never decoration, because in a trading interface a green
 * pill that does not mean "up" is actively misleading.
 */
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    container: { center: true, padding: "1.5rem", screens: { "2xl": "1600px" } },
    extend: {
      colors: {
        canvas: "hsl(var(--canvas) / <alpha-value>)",
        surface: "hsl(var(--surface) / <alpha-value>)",
        elevated: "hsl(var(--elevated) / <alpha-value>)",
        overlay: "hsl(var(--overlay) / <alpha-value>)",
        line: "hsl(var(--line) / <alpha-value>)",
        "line-strong": "hsl(var(--line-strong) / <alpha-value>)",

        ink: {
          DEFAULT: "hsl(var(--ink) / <alpha-value>)",
          muted: "hsl(var(--ink-muted) / <alpha-value>)",
          subtle: "hsl(var(--ink-subtle) / <alpha-value>)",
          faint: "hsl(var(--ink-faint) / <alpha-value>)",
        },

        primary: {
          DEFAULT: "hsl(var(--primary) / <alpha-value>)",
          foreground: "hsl(var(--primary-foreground) / <alpha-value>)",
        },
        accent: { DEFAULT: "hsl(var(--accent) / <alpha-value>)" },
        gain: { DEFAULT: "hsl(var(--gain) / <alpha-value>)" },
        loss: { DEFAULT: "hsl(var(--loss) / <alpha-value>)" },
        warn: { DEFAULT: "hsl(var(--warn) / <alpha-value>)" },
        info: { DEFAULT: "hsl(var(--info) / <alpha-value>)" },
      },
      borderRadius: { xl: "0.875rem", "2xl": "1.125rem", "3xl": "1.5rem" },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "0.875rem", letterSpacing: "0.02em" }],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.35), 0 8px 24px -12px rgb(0 0 0 / 0.55)",
        raised: "0 2px 4px 0 rgb(0 0 0 / 0.4), 0 16px 40px -16px rgb(0 0 0 / 0.65)",
        glow: "0 0 0 1px hsl(var(--primary) / 0.28), 0 8px 32px -8px hsl(var(--primary) / 0.35)",
      },
      backgroundImage: {
        "gradient-primary": "linear-gradient(135deg, hsl(var(--primary)) 0%, hsl(var(--accent)) 100%)",
        "gradient-glow": "radial-gradient(60% 60% at 50% 0%, hsl(var(--primary) / 0.16) 0%, transparent 70%)",
        grid: "linear-gradient(hsl(var(--line) / 0.5) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--line) / 0.5) 1px, transparent 1px)",
      },
      backgroundSize: { grid: "48px 48px" },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "fade-up": "fade-up 0.35s cubic-bezier(0.22, 1, 0.36, 1) both",
        shimmer: "shimmer 1.6s infinite",
      },
      transitionTimingFunction: { smooth: "cubic-bezier(0.22, 1, 0.36, 1)" },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
