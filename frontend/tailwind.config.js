/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      keyframes: {
        "fade-up": { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "none" } },
        "toast-in": { "0%": { opacity: "0", transform: "translateY(12px) scale(.98)" }, "100%": { opacity: "1", transform: "none" } },
        pop: { "0%": { transform: "scale(.6)" }, "60%": { transform: "scale(1.15)" }, "100%": { transform: "scale(1)" } },
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        dash: { to: { strokeDashoffset: "-40" } },
      },
      animation: {
        "fade-up": "fade-up .45s cubic-bezier(.2,.7,.2,1) both",
        "toast-in": "toast-in .3s cubic-bezier(.2,.7,.2,1) both",
        pop: "pop .35s ease-out both",
        float: "float 5s ease-in-out infinite",
        dash: "dash 2.5s linear infinite",
      },
    },
  },
  plugins: [],
};
