import { Beaker } from 'lucide-react'

interface SyntheticTabProps {
  onTrackingStateChange?: (isTracking: boolean) => void
}

export default function SyntheticTab(_props: SyntheticTabProps = {}) {
  return (
    <div className="space-y-6">
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Beaker className="w-5 h-5 text-primary-500" />
          Synthetic Data Generation
        </h2>

        <div className="text-center py-12">
          <Beaker className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-400 mb-2">Coming Soon</h3>
          <p className="text-gray-500">
            Synthetic data generation tools will be available in a future update.
          </p>
        </div>
      </div>
    </div>
  )
}
