import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          rose: '#C76B7E',
          'rose-dark': '#A84E63',
          'rose-soft': '#FCEFEF',
        },
        gold: {
          DEFAULT: '#B8995A',
          light: '#F3ECDC',
          dark: '#8A6F3C',
        },
        ink: '#2A2A2E',
        muted: '#6B6B73',
        line: '#F0E7E1',
        cream: '#FBF7F4',
        success: '#3F9D6D',
        warn: '#E0A23B',
        danger: '#D9534F',
      },
      fontFamily: {
        sans: ['-apple-system', 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
export default config;