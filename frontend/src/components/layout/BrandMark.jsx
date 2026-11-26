// EcoTrack mark: a floor plan cut into four rooms, one of them lit.
export default function BrandMark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true" className="shrink-0">
      <rect x="1.5" y="1.5" width="25" height="25" rx="3" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M14 1.5v25M1.5 14h25" stroke="currentColor" strokeWidth="2" />
      <rect x="15.5" y="3" width="9.5" height="9.5" fill="#e49b0f" />
    </svg>
  );
}
