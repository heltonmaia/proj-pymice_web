import { useState } from 'react'
import { Globe, Beaker, BarChart } from 'lucide-react'
import SyntheticTab from './SyntheticTab'

interface IRLTabProps {
  onTrackingStateChange?: (isTracking: boolean) => void
}

const subTabs = [
  { id: 'overview', label: 'Overview', icon: BarChart },
  { id: 'synthetic', label: 'Synthetic Data', icon: Beaker },
]

export default function IRLTab(props: IRLTabProps = {}) {
  const [activeSubTab, setActiveSubTab] = useState('overview')

  return (
    <div className="space-y-6">
      {/* Sub-tabs Navigation */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <div className="flex gap-2 p-2 border-b border-gray-700">
          {subTabs.map((subTab) => {
            const Icon = subTab.icon
            const isActive = activeSubTab === subTab.id

            return (
              <button
                key={subTab.id}
                onClick={() => setActiveSubTab(subTab.id)}
                className={`
                  flex items-center gap-2 px-4 py-2 rounded transition-colors whitespace-nowrap
                  ${isActive
                    ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50'
                  }
                `}
              >
                <Icon className="w-4 h-4" />
                <span className="text-sm font-medium">{subTab.label}</span>
              </button>
            )
          })}
        </div>

        {/* Sub-tab Content */}
        <div className="p-6">
          {activeSubTab === 'overview' && (
            <div>
              <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <Globe className="w-5 h-5 text-primary-500" />
                IRL (In Real Life) Analysis - Overview
              </h2>

              <div className="text-center py-12">
                <Globe className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-400 mb-2">Coming Soon</h3>
                <p className="text-gray-500">
                  Real-world experiment integration and analysis tools will be available in a future update.
                </p>
              </div>
            </div>
          )}

          {activeSubTab === 'synthetic' && (
            <SyntheticTab onTrackingStateChange={props.onTrackingStateChange} />
          )}
        </div>
      </div>
    </div>
  )
}
