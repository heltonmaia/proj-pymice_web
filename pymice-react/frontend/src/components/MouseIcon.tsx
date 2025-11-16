export default function MouseIcon({ className = "w-8 h-8" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 48"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {/* Mouse body (side view) */}
      <ellipse cx="24" cy="24" rx="16" ry="12"/>

      {/* Mouse head */}
      <circle cx="8" cy="20" r="6"/>

      {/* Mouse ear */}
      <path d="M 6 14 Q 4 10, 7 8 Q 10 10, 8 14" fill="none"/>

      {/* Mouse eye */}
      <circle cx="7" cy="19" r="1.2" fill="currentColor"/>

      {/* Mouse nose */}
      <circle cx="2" cy="21" r="1" fill="currentColor"/>

      {/* Mouse tail (curved, flowing back) */}
      <path d="M 40 26 Q 48 28, 54 24 Q 60 20, 62 14" strokeWidth="2"/>

      {/* Mouse legs (bottom, side view) */}
      <line x1="16" y1="36" x2="14" y2="42"/>
      <line x1="20" y1="36" x2="19" y2="43"/>
      <line x1="28" y1="36" x2="28" y2="43"/>
      <line x1="32" y1="36" x2="33" y2="42"/>
    </svg>
  )
}
