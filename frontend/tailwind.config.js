/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: 'rgba(255, 255, 255, 0.08)',
        secondary: '#94a3b8',
        primary: {
          DEFAULT: '#f8fafc',
          secondary: '#94a3b8',
        },
        accent: {
          gold: '#c5a059',
          'gold-dim': '#8a703e',
        },
        sky: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
        },
        atmospheric: {
          purple: '#c026d3',
          blue: '#4f46e5',
        },
        background: {
          DEFAULT: '#000000',
          atmospheric: {
            purple: '#c026d3',
            blue: '#4f46e5',
          }
        },
        // Dark theme colors for the animated component
        neutral: {
          50: '#fafafa',
          100: '#f5f5f5',
          200: '#e5e5e5',
          300: '#d4d4d4',
          400: '#a3a3a3',
          500: '#737373',
          600: '#525252',
          700: '#3f3f3f',
          800: '#272727',
          900: '#18181b',
          950: '#0a0a0b',
        },
        muted: {
          DEFAULT: '#737373',
          foreground: '#a3a3a3',
        },
        input: '#272727',
        ring: '#c026d3',
        violet: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#7c3aed',
          700: '#6d28d9',
          800: '#5b21b6',
          900: '#4c1d95',
        },
        indigo: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
        },
        fuchsia: {
          50: '#fdf4ff',
          100: '#fae8ff',
          200: '#f5d0fe',
          300: '#f0abfc',
          400: '#e879f9',
          500: '#d946ef',
          600: '#c026d3',
          700: '#a21caf',
          800: '#86198f',
          900: '#701a75',
        }
      },
      fontFamily: {
        'playfair': ['Playfair Display', 'serif'],
        'inter': ['Inter', 'sans-serif'],
        'cinzel': ['Cinzel', 'serif'],
      },
      backdropBlur: {
        xs: '2px',
      },
      keyframes: {
        'shimmer-sweep': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        'gradient-flow': {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        'thinking-pulse': {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.8' },
        },
        'dot-bounce': {
          '0%, 80%, 100%': { transform: 'translateY(0)', opacity: '0.4' },
          '40%': { transform: 'translateY(-3px)', opacity: '1' },
        },
        'liquid-morph': {
          '0%, 100%': { borderRadius: '24px', transform: 'scale(1)' },
          '33%': { borderRadius: '28px', transform: 'scale(1.02)' },
          '66%': { borderRadius: '20px', transform: 'scale(0.98)' },
        },
        'text-shimmer': {
          '0%': { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
      },
      animation: {
        'shimmer-sweep': 'shimmer-sweep 3s ease-in-out infinite',
        'gradient-flow': 'gradient-flow 6s ease infinite',
        'thinking-pulse': '3s ease-in-out infinite',
        'dot-bounce': 'dot-bounce 1.4s ease-in-out infinite',
        'liquid-morph': 'liquid-morph 8s ease-in-out infinite',
        'text-shimmer': 'text-shimmer 4s linear infinite',
      },
    },
  },
  plugins: [],
}
