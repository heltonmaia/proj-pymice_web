import { useState, useEffect } from 'react'

interface AnimatedMouseProps {
  trigger: any // Trigger animation when this value changes
}

export default function AnimatedMouse({ trigger }: AnimatedMouseProps) {
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => {
    // Don't run on initial mount
    if (trigger === undefined) return

    // Trigger animation
    setIsRunning(true)

    // Animation lasts 2.5 seconds, then hide
    const timer = setTimeout(() => {
      setIsRunning(false)
    }, 2500)

    return () => clearTimeout(timer)
  }, [trigger])

  if (!isRunning) return null

  return (
    <div className="absolute top-0 left-0 w-full h-full pointer-events-none z-10 overflow-hidden">
      <div className="animate-mouse-run" style={{ position: 'absolute', top: '1rem', left: '1rem' }}>
        <svg
          className="w-10 h-10 text-primary-400"
          viewBox="0 0 64 48"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ transform: 'scaleX(-1)' }}
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

          {/* Mouse legs (animated running) */}
          <g className="animate-legs">
            <line x1="16" y1="36" x2="14" y2="42"/>
            <line x1="20" y1="36" x2="19" y2="43"/>
            <line x1="28" y1="36" x2="28" y2="43"/>
            <line x1="32" y1="36" x2="33" y2="42"/>
          </g>
        </svg>
      </div>

      <style>{`
        @keyframes mouse-run {
          0% {
            transform: translateX(0);
            opacity: 1;
          }
          95% {
            opacity: 1;
          }
          100% {
            transform: translateX(calc(100vw - 4rem));
            opacity: 0;
          }
        }

        @keyframes legs-run {
          0%, 100% {
            transform: scaleY(1);
          }
          25% {
            transform: scaleY(0.8) translateY(2px);
          }
          50% {
            transform: scaleY(1.1) translateY(-1px);
          }
          75% {
            transform: scaleY(0.9) translateY(1px);
          }
        }

        .animate-mouse-run {
          animation: mouse-run 2.5s ease-in-out;
        }

        .animate-legs {
          transform-origin: center;
          animation: legs-run 0.25s infinite;
        }
      `}</style>
    </div>
  )
}
