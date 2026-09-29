import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(214 30% 88%)",
        input: "hsl(214 30% 88%)",
        ring: "hsl(221 83% 53%)",
        primary: "hsl(221 83% 53%)",
        "primary-foreground": "hsl(210 40% 98%)",
        background: "hsl(210 40% 98%)",
        foreground: "hsl(222 47% 11%)",
        card: "hsl(0 0% 100%)",
        "card-foreground": "hsl(222 47% 11%)",
        muted: "hsl(210 36% 94%)",
        "muted-foreground": "hsl(215 18% 40%)",
        accent: "hsl(210 36% 95%)",
        "accent-foreground": "hsl(222 47% 11%)",
        destructive: "hsl(0 72% 51%)",
        "destructive-foreground": "hsl(210 40% 98%)",
        "destructive-hover": "hsl(0 72% 43%)",
        "destructive-active": "hsl(0 72% 37%)",
        navy: {
          DEFAULT: "hsl(222 47% 11%)",
          foreground: "hsl(210 40% 98%)",
          muted: "hsl(215 25% 27%)",
          border: "hsl(215 22% 32%)",
        },
        rw: {
          frame: "hsl(214 32% 91%)",
          card: "hsl(0 0% 100%)",
          "panel-statement": "hsl(210 40% 99%)",
          "panel-sources": "hsl(214 40% 96%)",
          "panel-context": "hsl(38 60% 96%)",
          "panel-journey": "hsl(220 30% 95%)",
          "panel-verdict": "hsl(222 47% 11%)",
          "legal-text": "hsl(222 47% 11%)",
        },
        verdict: {
          accurate: "hsl(152 60% 36%)",
          incomplete: "hsl(38 92% 40%)",
          overreaching: "hsl(25 95% 45%)",
          "bad-merge": "hsl(0 72% 51%)",
          "missing-propositions": "hsl(262 60% 50%)",
        },
      },
      borderRadius: {
        lg: "0.75rem",
        md: "0.625rem",
        sm: "0.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
