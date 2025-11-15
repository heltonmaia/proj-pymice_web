import { useState, useRef } from 'react'
import { Upload, BarChart3, Download, ImageIcon } from 'lucide-react'
import type { TrackingData, HeatmapSettings } from '@/types'

export default function EthologicalTab() {
  const [trackingData, setTrackingData] = useState<TrackingData | null>(null)
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [heatmapSettings, setHeatmapSettings] = useState<HeatmapSettings>({
    resolution: 50,
    colormap: 'hot',
    transparency: 0.5,
  })
  const [analysisType, setAnalysisType] = useState<'complete' | 'heatmap' | 'movement'>('complete')
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const handleTrackingFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target?.result as string)
        setTrackingData(data)
      } catch (error) {
        console.error('Failed to parse tracking data:', error)
      }
    }
    reader.readAsText(file)
  }

  const handleGenerateAnalysis = () => {
    console.log('Generating analysis...', { trackingData, heatmapSettings, analysisType })
    // API call would go here
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-primary-500" />
          Ethological Analysis
        </h2>

        {/* File Upload Section */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Video File
            </label>
            <input
              type="file"
              accept="video/*"
              onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-600 file:text-white hover:file:bg-primary-700"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Tracking Data (JSON)
            </label>
            <input
              type="file"
              accept=".json"
              onChange={handleTrackingFileUpload}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-600 file:text-white hover:file:bg-primary-700"
            />
          </div>
        </div>

        {/* Analysis Type Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Analysis Type
          </label>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button
              onClick={() => setAnalysisType('complete')}
              className={`p-4 rounded-lg border-2 transition-colors ${
                analysisType === 'complete'
                  ? 'border-primary-500 bg-primary-900/30'
                  : 'border-gray-600 hover:border-gray-500'
              }`}
            >
              <div className="font-semibold mb-1">Complete Analysis</div>
              <div className="text-sm text-gray-400">
                Full panel with all metrics and visualizations
              </div>
            </button>

            <button
              onClick={() => setAnalysisType('heatmap')}
              className={`p-4 rounded-lg border-2 transition-colors ${
                analysisType === 'heatmap'
                  ? 'border-primary-500 bg-primary-900/30'
                  : 'border-gray-600 hover:border-gray-500'
              }`}
            >
              <div className="font-semibold mb-1">Heatmap Only</div>
              <div className="text-sm text-gray-400">
                Generate movement density heatmap
              </div>
            </button>

            <button
              onClick={() => setAnalysisType('movement')}
              className={`p-4 rounded-lg border-2 transition-colors ${
                analysisType === 'movement'
                  ? 'border-primary-500 bg-primary-900/30'
                  : 'border-gray-600 hover:border-gray-500'
              }`}
            >
              <div className="font-semibold mb-1">Movement Analysis</div>
              <div className="text-sm text-gray-400">
                Velocity and trajectory plots
              </div>
            </button>
          </div>
        </div>

        {/* Heatmap Settings */}
        {analysisType !== 'movement' && (
          <div className="bg-gray-700/50 rounded-lg p-4 mb-6">
            <h3 className="font-semibold mb-4">Heatmap Settings</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Resolution: {heatmapSettings.resolution}
                </label>
                <input
                  type="range"
                  min="20"
                  max="100"
                  step="10"
                  value={heatmapSettings.resolution}
                  onChange={(e) =>
                    setHeatmapSettings({
                      ...heatmapSettings,
                      resolution: parseInt(e.target.value),
                    })
                  }
                  className="w-full"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Colormap
                </label>
                <select
                  value={heatmapSettings.colormap}
                  onChange={(e) =>
                    setHeatmapSettings({
                      ...heatmapSettings,
                      colormap: e.target.value as HeatmapSettings['colormap'],
                    })
                  }
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                >
                  <option value="hot">Hot</option>
                  <option value="viridis">Viridis</option>
                  <option value="plasma">Plasma</option>
                  <option value="jet">Jet</option>
                  <option value="rainbow">Rainbow</option>
                  <option value="coolwarm">Cool Warm</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Transparency: {heatmapSettings.transparency.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={heatmapSettings.transparency}
                  onChange={(e) =>
                    setHeatmapSettings({
                      ...heatmapSettings,
                      transparency: parseFloat(e.target.value),
                    })
                  }
                  className="w-full"
                />
              </div>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-4">
          <button
            onClick={handleGenerateAnalysis}
            disabled={!trackingData || !videoFile}
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <ImageIcon className="w-5 h-5" />
            Generate Analysis
          </button>

          <button
            disabled={!trackingData}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Download className="w-5 h-5" />
            Export Results
          </button>
        </div>
      </div>

      {/* Results Preview */}
      {trackingData && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Analysis Preview</h3>
          <div className="bg-black rounded-lg overflow-hidden border border-gray-700">
            <canvas
              ref={canvasRef}
              className="w-full h-auto"
              style={{ maxHeight: '600px' }}
            />
          </div>

          {/* Statistics */}
          <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">Total Frames</div>
              <div className="text-2xl font-bold text-white">{trackingData.total_frames}</div>
            </div>
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">YOLO Detections</div>
              <div className="text-2xl font-bold text-green-400">{trackingData.yolo_detections}</div>
            </div>
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">Template Detections</div>
              <div className="text-2xl font-bold text-yellow-400">
                {trackingData.template_detections}
              </div>
            </div>
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">Missed Frames</div>
              <div className="text-2xl font-bold text-red-400">
                {trackingData.frames_without_detection}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
