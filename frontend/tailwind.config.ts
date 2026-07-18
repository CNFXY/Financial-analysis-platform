/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // FUND-OS 品牌色板
        gold: {
          DEFAULT: '#f0b020',
          50: '#fff9e6',
          100: '#ffefb3',
          200: '#ffe580',
          300: '#ffd94d',
          400: '#f0b020',
          500: '#d4940c',
          600: '#b07800',
          700: '#8a5c00',
          800: '#644200',
          900: '#3e2800',
        },
        cyan: {
          50: '#e6fcff',
          100: '#b3f5ff',
          200: '#80eeff',
          300: '#4de7ff',
          400: '#00d4ff',
          500: '#00b8e0',
          600: '#0098b8',
          700: '#007890',
          800: '#005868',
          900: '#003840',
        },
        surface: {
          DEFAULT: '#0c1428',
          light: '#111d38',
          dark: '#060a14',
          deep: '#04060d',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      animation: {
        'shimmer': 'shimmer 2s linear infinite',
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan': 'scan 8s linear infinite',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        fadeInUp: {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        scan: {
          '0%': { top: '-200px' },
          '100%': { top: 'calc(100vh + 200px)' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from var(--tw-gradient-start) at var(--tw-gradient-pos), var(--tw-gradient-stops))',
        'grid-pattern':
          "linear-gradient(rgba(240,176,32,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(240,176,32,0.04) 1px, transparent 1px)",
      },
      backgroundSize: {
        grid: '60px 60px',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
}
