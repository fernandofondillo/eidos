/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        eidos: {
          bg: '#0d1117',
          surface: '#161b22',
          border: '#30363d',
          primary: '#6db33f',
          accent: '#58a6ff',
          warning: '#f0883e',
          danger: '#f85149',
          text: '#e6edf3',
          muted: '#8b949e',
        },
      },
    },
  },
  plugins: [],
};
