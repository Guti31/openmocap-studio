/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        studio: {
          bg: '#0b0f17',
          panel: '#111827',
          elevated: '#182235',
          border: '#1f2937',
          accent: '#06b6d4',
          ok: '#10b981',
          warn: '#f59e0b',
          danger: '#ef4444',
        },
      },
    },
  },
  plugins: [],
};

