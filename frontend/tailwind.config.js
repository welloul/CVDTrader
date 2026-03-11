/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                hyper: '#0b0e14', // Example dark hyperliquid-like bg
                panel: '#151924',
                accent: '#2ebd85',
                danger: '#e0294a',
                muted: '#8e9eac'
            }
        },
    },
    plugins: [],
}
