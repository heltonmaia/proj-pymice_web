import type { ExperimentEvent } from '@/types'

interface Props { events: ExperimentEvent[] }

export default function EventLogPanel({ events }: Props) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <h3 className="font-semibold mb-2">Event Log</h3>
      <div className="text-xs font-mono space-y-1 max-h-64 overflow-auto">
        {events.slice(-100).map((e, i) => (
          <div key={i}>
            <span className="text-gray-500">{e.t?.toFixed(2) ?? '—'}s</span>{' '}
            <span className="text-primary-600">{e.type}</span>{' '}
            <span>{JSON.stringify({ ...e, type: undefined, t: undefined })}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
