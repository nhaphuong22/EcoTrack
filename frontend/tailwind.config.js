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
        ground: '#edf3f1',
        panel: '#ffffff',
        sunken: '#f3f7f5',
        line: '#dde6e3',
        'line-strong': '#bcc9c4',
        ink: '#0e1e1d',
        'ink-2': '#334642',
        muted: '#52635d',
        faint: '#788883',
        shell: '#0c3a3e',
        'shell-2': '#135056',
        'shell-line': '#2b6469',
        'shell-ink': '#e2efec',
        'shell-muted': '#9dbdb8',
        signal: '#1f55cc',
        'signal-bg': '#e6eefc',
        ok: '#147246',
        'ok-bg': '#dcf3e7',
        warn: '#8f5400',
        'warn-fill': '#e49b0f',
        'warn-bg': '#fef2d6',
        crit: '#b9222c',
        'crit-bg': '#fde6e6',
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
