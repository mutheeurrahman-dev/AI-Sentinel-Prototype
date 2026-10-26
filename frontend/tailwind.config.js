/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0B1220",
          900: "#101B30",
          800: "#182640",
          700: "#22334F",
        },
        paper: {
          50: "#FBFAF6",
          100: "#F5F2EA",
          200: "#EBE6D8",
        },
        marigold: {
          500: "#C97A2B",
          600: "#B0651C",
        },
        risk: {
          high: "#B4231E",
          medium: "#B0651C",
          low: "#2F6B4F",
        },
      },
      fontFamily: {
        serif: ["'Source Serif 4'", "Georgia", "serif"],
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
    },
  },
  plugins: [],
}

