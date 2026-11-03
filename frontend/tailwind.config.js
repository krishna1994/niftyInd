module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Trading terminal colors
        bg: {
          primary: "#0a0e1a",
          secondary: "#0f1629",
          tertiary: "#1a2035",
        },
        accent: {
          bullish: "#00d4aa",
          bearish: "#ff4757",
          neutral: "#ffa502",
        },
        text: {
          primary: "#e8eaf6",
          muted: "#546e7a",
        },
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "monospace"],
        sans: ["'DM Sans'", "'Sora'", "sans-serif"],
      },
    },
  },
  plugins: [],
}
