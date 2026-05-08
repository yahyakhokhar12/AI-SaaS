/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f1115",
        panel: "#141923",
        panelSoft: "#181f2b",
        line: "#2a3342",
        accent: "#10a37f",
      },
    },
  },
  plugins: [],
};
