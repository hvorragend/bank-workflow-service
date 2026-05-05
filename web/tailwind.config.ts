import type { Config } from "tailwindcss";

// Editorial-Design-Tokens aus dem Vue-Vorgaenger. Das Off-White, der
// Akzent-Bordeaux, die Serif/Sans/Mono-Trias bleiben — wir uebersetzen die
// CSS-Variablen lediglich in Tailwind-Theme-Eintraege.

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1180px" } },
    extend: {
      colors: {
        bg:           "hsl(38 50% 94%)",   // #f4f0e8 warmes Off-White
        paper:        "hsl(0 0% 100%)",
        rule:         "hsl(40 18% 80%)",
        "rule-soft":  "hsl(43 30% 87%)",
        ink:          "hsl(30 10% 9%)",
        muted:        "hsl(35 6% 41%)",
        quiet:        "hsl(35 7% 57%)",
        accent:       "hsl(0 53% 31%)",   // Bordeaux
        "accent-soft":"hsl(15 80% 93%)",
        ok:           "hsl(135 35% 27%)",
        "ok-soft":    "hsl(110 22% 92%)",
        warn:         "hsl(40 75% 31%)",
        "warn-soft":  "hsl(46 71% 88%)",
        bad:          "hsl(0 53% 31%)",
        "bad-soft":   "hsl(13 64% 89%)",
        neutral:      "hsl(218 18% 28%)",
        "neutral-soft":"hsl(220 13% 91%)",
      },
      fontFamily: {
        display: ['"Fraunces"', '"Iowan Old Style"', "Georgia", "serif"],
        body:    ['"Public Sans"', "-apple-system", '"Segoe UI"', "sans-serif"],
        mono:    ['"JetBrains Mono"', "ui-monospace", '"SF Mono"', "monospace"],
      },
      borderRadius: { none: "0", sm: "2px", DEFAULT: "2px", md: "3px", lg: "4px" },
      letterSpacing: { tightish: "-0.01em" },
      keyframes: {
        slidein: {
          from: { transform: "translateY(20px)", opacity: "0" },
          to:   { transform: "translateY(0)",    opacity: "1" },
        },
      },
      animation: { slidein: "slidein 200ms ease-out" },
    },
  },
  plugins: [],
} satisfies Config;
