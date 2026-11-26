/** @type {import('tailwindcss').Config} */
// Palette: a daylit building-operations room. Petrol shell, cool-tinted paper,
// and three state colours that only ever mean something (ok / warn / crit).
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ground: '#e8edeb',
        panel: '#fafcfb',
        sunken: '#f0f4f2',
        line: '#d2dbd8',
        'line-strong': '#a9b8b3',
        ink: '#0e1e1d',
        'ink-2': '#3b4d4a',
        muted: '#54655f',
        faint: '#7c8b87',
        shell: '#0c3a3e',
        'shell-2': '#135056',
        'shell-line': '#2b6469',
        'shell-ink': '#e2efec',
        'shell-muted': '#9dbdb8',
        signal: '#1f55cc',
        'signal-bg': '#e3ebfb',
        ok: '#17784a',
        'ok-bg': '#dcf0e4',
        warn: '#8f5400',
        'warn-fill': '#e49b0f',
        'warn-bg': '#fbecc9',
        crit: '#bd2630',
        'crit-bg': '#fbdedb',
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
