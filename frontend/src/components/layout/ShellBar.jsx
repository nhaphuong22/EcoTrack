import BrandMark from './BrandMark';

// Top shell shared by every signed-in view. `context` is who/where, children are the actions.
export default function ShellBar({ context, navLabel, children }) {
  return (
    <header className="sticky top-0 z-30 bg-shell text-shell-ink">
      <div className="mx-auto flex min-h-14 max-w-screen-2xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-2 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <BrandMark />
          <span className="text-base font-bold tracking-tight text-white">EcoTrack</span>
          {context && (
            <>
              <span className="hidden h-5 w-px bg-shell-line sm:block" aria-hidden="true" />
              <span className="text-sm text-shell-muted">{context}</span>
            </>
          )}
        </div>
        <nav aria-label={navLabel} className="flex flex-wrap items-center gap-2">
          {children}
        </nav>
      </div>
    </header>
  );
}
