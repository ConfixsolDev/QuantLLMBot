import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        gold: "#d4a017",
        panel: "#111827",
        ink: "#0b0f17",
      },
    },
  },
  plugins: [],
};

export default config;
