import { useState } from 'react'
import { Camera, Target, BarChart3, Wrench, Beaker, Globe } from 'lucide-react'
import MouseIcon from './components/MouseIcon'
import AnimatedMouse from './components/AnimatedMouse'
import CameraTab from './pages/CameraTab'
import TrackingTab from './pages/TrackingTab'
import EthologicalTab from './pages/EthologicalTab'
import ExtraToolsTab from './pages/ExtraToolsTab'
import SyntheticTab from './pages/SyntheticTab'
import IRLTab from './pages/IRLTab'

const tabs = [
  { id: 'camera', label: 'Camera', icon: Camera, component: CameraTab },
  { id: 'tracking', label: 'Tracking', icon: Target, component: TrackingTab },
  { id: 'ethological', label: 'Ethological Analysis', icon: BarChart3, component: EthologicalTab },
  { id: 'extra', label: 'Extra Tools', icon: Wrench, component: ExtraToolsTab },
  { id: 'synthetic', label: 'Synthetic Data', icon: Beaker, component: SyntheticTab },
  { id: 'irl', label: 'IRL Analysis', icon: Globe, component: IRLTab },
]

function App() {
  const [activeTab, setActiveTab] = useState('camera')
  const [isTrackingActive, setIsTrackingActive] = useState(false)

  const ActiveComponent = tabs.find(tab => tab.id === activeTab)?.component || CameraTab

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 sticky top-0 z-50 relative">
        {/* Animated Mouse */}
        <AnimatedMouse trigger={activeTab} />

        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <MouseIcon className="w-10 h-10 text-primary-500" style={{ transform: 'scaleX(-1)' }} />
              <div>
                <h1 className="text-2xl font-bold text-white">PyMiceTracking</h1>
                <p className="text-sm text-gray-400">Web Application for Mice Behavioral Analysis</p>
              </div>
            </div>
            <div className="text-sm text-gray-400">
              v1.0.0
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="container mx-auto px-4">
          <div className="flex gap-2 overflow-x-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon
              const isCurrentTab = activeTab === tab.id
              const isDisabled = isTrackingActive && !isCurrentTab

              return (
                <button
                  key={tab.id}
                  onClick={() => !isDisabled && setActiveTab(tab.id)}
                  disabled={isDisabled}
                  className={`
                    flex items-center gap-2 px-4 py-3 border-b-2 transition-colors whitespace-nowrap
                    ${isCurrentTab
                      ? 'border-primary-500 text-primary-400 bg-gray-700/50'
                      : isDisabled
                        ? 'border-transparent text-gray-600 cursor-not-allowed opacity-50'
                        : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-700/30'
                    }
                  `}
                >
                  <Icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{tab.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <ActiveComponent onTrackingStateChange={setIsTrackingActive} />
      </main>

      {/* Footer */}
      <footer className="bg-gray-800 border-t border-gray-700 mt-12">
        <div className="container mx-auto px-4 py-6 text-center text-sm text-gray-400">
          <p>PyMiceTracking Web - Behavioral Analysis Platform</p>
          <p className="mt-1">Built with React + TypeScript + FastAPI</p>
        </div>
      </footer>
    </div>
  )
}

export default App
