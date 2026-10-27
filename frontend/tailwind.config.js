const scale = (name, steps) =>
  Object.fromEntries(steps.map((s) => [s, `var(--fsp-${name}-${s})`]));

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "var(--fsp-primary-500)",
          ...scale("primary", [50, 100, 200, 300, 400, 500, 600, 700, 900]),
        },
        neutral: scale("neutral", [0, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900]),
        success: { DEFAULT: "var(--fsp-success-500)", ...scale("success", [50, 500, 700]) },
        warning: { DEFAULT: "var(--fsp-warning-500)", ...scale("warning", [50, 500, 700]) },
        danger: { DEFAULT: "var(--fsp-danger-500)", ...scale("danger", [50, 500, 700]) },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "Consolas", "monospace"],
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        pill: "var(--radius-pill)",
      },
    },
  },
  plugins: [],
};
