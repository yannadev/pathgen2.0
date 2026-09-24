export default {
  content: [
    "./templates/**/*.html",
    "./static/src/js/**/*.js",
    "./node_modules/preline/dist/*.js",
  ],
  darkMode: "class",
  theme: {
    screens: {
      xs: "475px",
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1536px",
    },
    extend: {
      fontFamily: {
        sans: ["Geist", "system-ui", "sans-serif"],
      },
    },
  },
};
