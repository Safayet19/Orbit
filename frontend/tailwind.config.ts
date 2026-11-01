import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        orbit: {
          bg: "#0B1017",
          sidebar: "#101720",
          surface: "#171F2A",
          elevated: "#283341",
          border: "#354052",
          strong: "#526176",
          copper: "#FFAD73",
          info: "#69BAFF",
          success: "#47D7A5",
          error: "#FF7185",
          warning: "#FFC46B",
          regular: "#E2E8F0",
          secondary: "#D4DEEA",
          muted: "#BFCBDD",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
