import { useState, useRef, useEffect } from 'react'
import { Upload, BarChart3, Download, ImageIcon, ChevronDown, ChevronUp } from 'lucide-react'
import type { TrackingData, HeatmapSettings } from '@/types'
import { analysisApi } from '@/services/api'

interface EthologicalTabProps {
  onTrackingStateChange?: (isTracking: boolean) => void
}

export default function EthologicalTab({ onTrackingStateChange }: EthologicalTabProps = {}) {
  const [trackingData, setTrackingData] = useState<TrackingData | null>(null)
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [heatmapSettings, setHeatmapSettings] = useState<HeatmapSettings>({
    resolution: 50,
    colormap: 'hot',
    transparency: 0.5,
    movement_threshold_percentile: 75,
    velocity_bins: 50,
    gaussian_sigma: 1.0,
    moving_average_window: 30,
  })
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [showBehavioralSettings, setShowBehavioralSettings] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [analysisLogs, setAnalysisLogs] = useState<Array<{ time: string; message: string; type: 'info' | 'error' | 'success' }>>([])
  const logsEndRef = useRef<HTMLDivElement>(null)

  // Behavioral Analysis States
  const [selectedBehavioralTest, setSelectedBehavioralTest] = useState<'open_field' | 'elevated_plus_maze' | null>(null)
  const [openFieldAnalyses, setOpenFieldAnalyses] = useState({
    rearing: false,
    edgeJumps: false,
    resting: false,
    grooming: false,
  })
  const [elevatedPlusMazeAnalyses, setElevatedPlusMazeAnalyses] = useState({
    suddenRun: false,
    panoramicView: false,
    headDips: false,
    grooming: false,
  })

  // Lock tab when analyzing
  useEffect(() => {
    onTrackingStateChange?.(isAnalyzing)
  }, [isAnalyzing, onTrackingStateChange])

  const addLog = (message: string, type: 'info' | 'error' | 'success' = 'info') => {
    const time = new Date().toLocaleTimeString()
    setAnalysisLogs(prev => [...prev, { time, message, type }])
    setTimeout(() => {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }

  const handleTrackingFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    addLog(`Loading tracking data from ${file.name}...`, 'info')
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target?.result as string)
        setTrackingData(data)
        addLog(`Tracking data loaded successfully: ${data.tracking_data?.length || 0} frames`, 'success')
      } catch (error) {
        console.error('Failed to parse tracking data:', error)
        addLog('Failed to parse tracking data: ' + (error as Error).message, 'error')
      }
    }
    reader.readAsText(file)
  }

  const handleRunAnalysis = async () => {
    if (!trackingData) {
      addLog('No tracking data loaded', 'error')
      return
    }

    setIsAnalyzing(true)
    setAnalysisResult(null)
    addLog('Starting complete analysis (heatmap + movement)...', 'info')
    addLog('Settings: ' + JSON.stringify(heatmapSettings), 'info')

    try {
      // Generate complete analysis panel
      const response = await analysisApi.generateCompleteAnalysis({
        tracking_data: trackingData,
        settings: heatmapSettings,
      })

      // Create image URL from blob
      const imageUrl = URL.createObjectURL(response.data)
      setAnalysisResult(imageUrl)

      // Display on canvas
      const canvas = canvasRef.current
      if (canvas) {
        const ctx = canvas.getContext('2d')
        const img = new Image()
        img.onload = () => {
          canvas.width = img.width
          canvas.height = img.height
          ctx?.drawImage(img, 0, 0)
          addLog('Complete analysis generated and displayed successfully', 'success')
        }
        img.src = imageUrl
      }
    } catch (error: any) {
      console.error('Failed to generate analysis:', error)
      const errorMsg = error.response?.data?.detail || error.message || 'Unknown error'
      addLog(`Analysis failed: ${errorMsg}`, 'error')

      // Log additional error details if available
      if (error.response?.status) {
        addLog(`HTTP ${error.response.status}: ${JSON.stringify(error.response.data)}`, 'error')
      }
    } finally {
      setIsAnalyzing(false)
    }
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

        {/* Movement Analysis */}
        <div className="bg-gray-700/50 rounded-lg p-4 mb-6">
            <div
              className="flex items-center justify-between cursor-pointer hover:bg-gray-600/30 -m-4 p-4 rounded-lg transition-colors"
              onClick={() => setShowSettings(!showSettings)}
            >
              <div>
                <h3 className="font-semibold text-lg">Movement Analysis</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Configure parameters for heatmap generation and velocity analysis
                </p>
              </div>
              {showSettings ? (
                <ChevronUp className="w-5 h-5 text-gray-400" />
              ) : (
                <ChevronDown className="w-5 h-5 text-gray-400" />
              )}
            </div>

            {showSettings && (
              <>
                <h4 className="font-medium text-gray-300 mb-3 mt-6">Heatmap Configuration</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Gaussian Smoothing: {heatmapSettings.gaussian_sigma?.toFixed(1)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="3"
                  step="0.5"
                  value={heatmapSettings.gaussian_sigma}
                  onChange={(e) =>
                    setHeatmapSettings({
                      ...heatmapSettings,
                      gaussian_sigma: parseFloat(e.target.value),
                    })
                  }
                  className="w-full"
                />
                <p className="text-xs text-gray-400 mt-1">
                  Sigma for Gaussian filter
                </p>
              </div>
            </div>

            <h4 className="font-medium text-gray-300 mb-3 mt-6">Velocity Analysis Parameters</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Movement Threshold: {heatmapSettings.movement_threshold_percentile}th percentile
                </label>
                <input
                  type="range"
                  min="50"
                  max="95"
                  step="5"
                  value={heatmapSettings.movement_threshold_percentile}
                  onChange={(e) =>
                    setHeatmapSettings({
                      ...heatmapSettings,
                      movement_threshold_percentile: parseInt(e.target.value),
                    })
                  }
                  className="w-full"
                />
                <p className="text-xs text-gray-400 mt-1">
                  Velocities above this percentile are considered "moving"
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Velocity Histogram Bins: {heatmapSettings.velocity_bins}
                </label>
                <input
                  type="range"
                  min="20"
                  max="100"
                  step="10"
                  value={heatmapSettings.velocity_bins}
                  onChange={(e) =>
                    setHeatmapSettings({
                      ...heatmapSettings,
                      velocity_bins: parseInt(e.target.value),
                    })
                  }
                  className="w-full"
                />
                <p className="text-xs text-gray-400 mt-1">
                  Number of bins for velocity distribution
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Moving Average Window: {heatmapSettings.moving_average_window}
                </label>
                <input
                  type="range"
                  min="5"
                  max="200"
                  step="5"
                  value={heatmapSettings.moving_average_window}
                  onChange={(e) =>
                    setHeatmapSettings({
                      ...heatmapSettings,
                      moving_average_window: parseInt(e.target.value),
                    })
                  }
                  className="w-full"
                />
                <p className="text-xs text-gray-400 mt-1">
                  Number of frames for velocity smoothing
                </p>
              </div>
            </div>

            <div className="bg-gray-600/30 rounded p-3 mt-4">
              <p className="text-xs text-gray-300">
                <span className="font-semibold">Analyses performed:</span> Movement heatmap with trajectory overlay,
                velocity over time, velocity distribution, activity classification (moving vs stationary)
              </p>
            </div>
          </>
        )}
        </div>

        {/* Behavioral Analysis */}
        <div className="bg-gray-700/50 rounded-lg p-4 mb-6">
          <div
            className="flex items-center justify-between cursor-pointer hover:bg-gray-600/30 -m-4 p-4 rounded-lg transition-colors"
            onClick={() => setShowBehavioralSettings(!showBehavioralSettings)}
          >
            <div>
              <h3 className="font-semibold text-lg">Behavioral Analysis</h3>
              <p className="text-sm text-gray-400 mt-1">
                Advanced behavioral classification and pattern recognition (Coming soon)
              </p>
            </div>
            {showBehavioralSettings ? (
              <ChevronUp className="w-5 h-5 text-gray-400" />
            ) : (
              <ChevronDown className="w-5 h-5 text-gray-400" />
            )}
          </div>

          {showBehavioralSettings && (
            <div className="mt-6 space-y-6">
              {/* Test Selection */}
              <div>
                <h4 className="font-medium text-gray-300 mb-3">Select Behavioral Test</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Open Field */}
                  <button
                    onClick={() => setSelectedBehavioralTest(selectedBehavioralTest === 'open_field' ? null : 'open_field')}
                    className={`p-4 rounded-lg border-2 transition-all text-left ${
                      selectedBehavioralTest === 'open_field'
                        ? 'border-primary-500 bg-primary-500/10'
                        : 'border-gray-600 bg-gray-700/30 hover:border-gray-500'
                    }`}
                  >
                    <h5 className="font-semibold text-white mb-1">OPEN FIELD (Round)</h5>
                    <p className="text-sm text-gray-400">Circular arena behavior analysis</p>
                  </button>

                  {/* Elevated Plus Maze */}
                  <button
                    onClick={() => setSelectedBehavioralTest(selectedBehavioralTest === 'elevated_plus_maze' ? null : 'elevated_plus_maze')}
                    className={`p-4 rounded-lg border-2 transition-all text-left ${
                      selectedBehavioralTest === 'elevated_plus_maze'
                        ? 'border-primary-500 bg-primary-500/10'
                        : 'border-gray-600 bg-gray-700/30 hover:border-gray-500'
                    }`}
                  >
                    <h5 className="font-semibold text-white mb-1">ELEVATED PLUS MAZE</h5>
                    <p className="text-sm text-gray-400">Anxiety and exploration test</p>
                  </button>
                </div>
              </div>

              {/* Open Field Analyses */}
              {selectedBehavioralTest === 'open_field' && (
                <div className="bg-gray-700/30 rounded-lg p-4 border border-gray-600">
                  <h4 className="font-medium text-gray-300 mb-3">Open Field Analyses</h4>
                  <div className="space-y-3">
                    <label className="flex items-center gap-3 cursor-pointer hover:bg-gray-600/20 p-2 rounded transition-colors">
                      <input
                        type="checkbox"
                        checked={openFieldAnalyses.rearing}
                        onChange={(e) => setOpenFieldAnalyses({ ...openFieldAnalyses, rearing: e.target.checked })}
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-white font-medium">Rearing</span>
                        <p className="text-xs text-gray-400">Implementation of 3 ROIs (central area, lower edge, upper edge) quantifying when the animal's body partially crosses the lower edge</p>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-2 rounded opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={openFieldAnalyses.edgeJumps}
                        onChange={(e) => setOpenFieldAnalyses({ ...openFieldAnalyses, edgeJumps: e.target.checked })}
                        disabled
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-gray-400 font-medium">Edge Jumps</span>
                        <p className="text-xs text-gray-500">Track jumping attempts at arena borders (Coming soon)</p>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-2 rounded opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={openFieldAnalyses.resting}
                        onChange={(e) => setOpenFieldAnalyses({ ...openFieldAnalyses, resting: e.target.checked })}
                        disabled
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-gray-400 font-medium">Resting</span>
                        <p className="text-xs text-gray-500">Identify stationary/resting periods (Coming soon)</p>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-2 rounded opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={openFieldAnalyses.grooming}
                        onChange={(e) => setOpenFieldAnalyses({ ...openFieldAnalyses, grooming: e.target.checked })}
                        disabled
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-gray-400 font-medium">Grooming</span>
                        <p className="text-xs text-gray-500">Detect self-grooming behavior (Coming soon)</p>
                      </div>
                    </label>
                  </div>
                </div>
              )}

              {/* Elevated Plus Maze Content */}
              {selectedBehavioralTest === 'elevated_plus_maze' && (
                <div className="bg-gray-700/30 rounded-lg p-4 border border-gray-600">
                  <h4 className="font-medium text-gray-300 mb-3">Elevated Plus Maze Analyses</h4>
                  <div className="space-y-3">
                    <label className="flex items-center gap-3 p-2 rounded opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={elevatedPlusMazeAnalyses.suddenRun}
                        onChange={(e) => setElevatedPlusMazeAnalyses({ ...elevatedPlusMazeAnalyses, suddenRun: e.target.checked })}
                        disabled
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-gray-400 font-medium">Sudden Run</span>
                        <p className="text-xs text-gray-500">Detect sudden rapid movements (Coming soon)</p>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-2 rounded opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={elevatedPlusMazeAnalyses.panoramicView}
                        onChange={(e) => setElevatedPlusMazeAnalyses({ ...elevatedPlusMazeAnalyses, panoramicView: e.target.checked })}
                        disabled
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-gray-400 font-medium">Panoramic View</span>
                        <p className="text-xs text-gray-500">Track head scanning and environment observation (Coming soon)</p>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-2 rounded opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={elevatedPlusMazeAnalyses.headDips}
                        onChange={(e) => setElevatedPlusMazeAnalyses({ ...elevatedPlusMazeAnalyses, headDips: e.target.checked })}
                        disabled
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-gray-400 font-medium">Head Dips</span>
                        <p className="text-xs text-gray-500">Identify head dipping over edges (Coming soon)</p>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-2 rounded opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={elevatedPlusMazeAnalyses.grooming}
                        onChange={(e) => setElevatedPlusMazeAnalyses({ ...elevatedPlusMazeAnalyses, grooming: e.target.checked })}
                        disabled
                        className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800"
                      />
                      <div>
                        <span className="text-gray-400 font-medium">Grooming</span>
                        <p className="text-xs text-gray-500">Detect self-grooming behavior (Coming soon)</p>
                      </div>
                    </label>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex gap-4">
          <button
            onClick={handleRunAnalysis}
            disabled={!trackingData || isAnalyzing}
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <ImageIcon className="w-5 h-5" />
            {isAnalyzing ? 'Running Analysis...' : 'Run Analysis'}
          </button>

          <button
            onClick={async () => {
              if (!trackingData) return

              try {
                addLog('Generating download package...', 'info')
                const response = await analysisApi.downloadCompleteAnalysis({
                  tracking_data: trackingData,
                  settings: heatmapSettings,
                })

                // Create download link for ZIP
                const url = URL.createObjectURL(response.data)
                const link = document.createElement('a')
                link.href = url
                link.download = `complete_analysis_${new Date().getTime()}.zip`
                link.click()
                URL.revokeObjectURL(url)

                addLog('Downloaded ZIP with: 4 images + enhanced JSON with velocity data', 'success')
              } catch (error: any) {
                addLog(`Download failed: ${error.message}`, 'error')
              }
            }}
            disabled={!trackingData}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Download className="w-5 h-5" />
            Download Results (ZIP)
          </button>
        </div>
      </div>

      {/* Results Preview */}
      {trackingData && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Analysis Preview</h3>
          <div className="bg-black rounded-lg overflow-hidden border border-gray-700 flex items-center justify-center" style={{ minHeight: '400px' }}>
            <canvas
              ref={canvasRef}
              style={{ maxWidth: '100%', maxHeight: '600px', height: 'auto', width: 'auto' }}
            />
          </div>

          {/* Statistics */}
          <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">Total Frames</div>
              <div className="text-2xl font-bold text-white">{trackingData.video_info.total_frames}</div>
            </div>
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">YOLO Detections</div>
              <div className="text-2xl font-bold text-green-400">{trackingData.statistics.yolo_detections}</div>
            </div>
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">Template Detections</div>
              <div className="text-2xl font-bold text-yellow-400">
                {trackingData.statistics.template_detections}
              </div>
            </div>
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="text-sm text-gray-400">Missed Frames</div>
              <div className="text-2xl font-bold text-red-400">
                {trackingData.statistics.frames_without_detection}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Analysis Log */}
      {analysisLogs.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Analysis Log</h3>
          <div className="bg-black rounded-lg p-4 border border-gray-700 max-h-64 overflow-y-auto font-mono text-sm">
            {analysisLogs.map((log, index) => (
              <div key={index} className={`mb-1 ${
                log.type === 'error' ? 'text-red-400' :
                log.type === 'success' ? 'text-green-400' :
                'text-gray-300'
              }`}>
                <span className="text-gray-500">[{log.time}]</span> {log.message}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}
    </div>
  )
}
