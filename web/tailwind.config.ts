import type { Config } from "tailwindcss";

// Design-Tokens im Stil der Volksbanken Raiffeisenbanken:
// Tiefes Markenblau als Primaerfarbe, Orange als Akzent, klares Weiss/Grau
// als ruhige Grundflaeche. Die Schrift ist eine moderne Sans (Inter).

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1rem", sm: "1.5rem", lg: "2rem" },
      screens: { "2xl": "1240px" },
    },
    extend: {
      colors: {
        bg:           "hsl(210 25% 98%)",   // sehr helles, leicht kuehles Weiss
        paper:        "hsl(0 0% 100%)",
        rule:         "hsl(214 15% 88%)",
        "rule-soft":  "hsl(214 20% 93%)",
        ink:          "hsl(215 28% 14%)",
        muted:        "hsl(215 14% 38%)",
        quiet:        "hsl(215 12% 45%)",  // abgedunkelt fuer WCAG-Kontrast (U-009)

        // Markenblau (Volksbanken-Stil)
        accent:        "hsl(212 100% 21%)",  // #003269
        "accent-hover":"hsl(212 100% 17%)",
        "accent-soft": "hsl(212 60% 94%)",
        "accent-ring": "hsl(212 100% 35%)",

        // Markenorange (BVR-Akzent)
        brand:         "hsl(33 100% 48%)",   // #f39200
        "brand-soft":  "hsl(33 100% 94%)",

        ok:            "hsl(150 55% 32%)",
        "ok-soft":     "hsl(150 45% 92%)",
        warn:          "hsl(33 100% 38%)",
        "warn-soft":   "hsl(38 100% 92%)",
        bad:           "hsl(0 72% 45%)",
        "bad-soft":    "hsl(0 80% 95%)",
        neutral:       "hsl(215 18% 32%)",
        "neutral-soft":"hsl(215 18% 92%)",
      },
      fontFamily: {
        display: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        body:    ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono:    ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        none: "0",
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        "2xl": "20px",
      },
      boxShadow: {
        card:  "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.06)",
        pop:   "0 8px 24px -8px rgb(15 23 42 / 0.18), 0 2px 6px 0 rgb(15 23 42 / 0.06)",
        ring:  "0 0 0 3px hsl(212 100% 35% / 0.18)",
      },
      letterSpacing: { tightish: "-0.01em" },
      keyframes: {
        slidein: {
          from: { transform: "translateY(20px)", opacity: "0" },
          to:   { transform: "translateY(0)",    opacity: "1" },
        },
        fadein: {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
      },
      animation: {
        slidein: "slidein 220ms ease-out",
        fadein:  "fadein 160ms ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
