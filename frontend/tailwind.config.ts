import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#0D1117",
          light: "#111827",
          deep: "#0B0F14",
          card: "#141A22",
          edge: "#1C2430",
        },
        gold: {
          DEFAULT: "#F59E0B",
          light: "#FBBF24",
          soft: "#FDE68A",
        },
        paper: "#E8E8E8",
        muted: "#9CA3AF",
        danger: "#EF4444",
      },
      fontFamily: {
        mono: ["Fira Code", "JetBrains Mono", "monospace"],
        sans: ["Inter", "Sora", "system-ui", "sans-serif"],
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "0.55", transform: "scale(1)" },
          "50%": { opacity: "0.9", transform: "scale(1.05)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.2" },
        },
        growBar: {
          from: { transform: "scaleY(0)" },
          to: { transform: "scaleY(1)" },
        },
        drawLine: {
          from: { strokeDashoffset: "1" },
          to: { strokeDashoffset: "0" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-800px 0" },
          "100%": { backgroundPosition: "800px 0" },
        },
        ticker: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
      animation: {
        "pulse-glow": "pulseGlow 3.5s ease-in-out infinite",
        blink: "blink 1.4s ease-in-out infinite",
        "grow-bar": "growBar 0.9s ease-out forwards",
        shimmer: "shimmer 1.6s linear infinite",
        ticker: "ticker 38s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
