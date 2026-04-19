import { useState, useRef, useEffect } from 'react'
import { Upload, Play, Pause, SkipBack, SkipForward, Eye, Settings, X, Loader2 } from 'lucide-react'
import type { TrackingData, ROI } from '@/types'
import { analysisApi } from '@/services/api'

interface VisualizarResultadosTabProps {
  onTrackingStateChange?: (isTracking: boolean) => void
}

export default function VisualizarResultadosTab(_props: VisualizarResultadosTabProps = {}) {
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [trackingData, setTrackingData] = useState<TrackingData | null>(null)
  const [jsonFileName, setJsonFileName] = useState<string>('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentFrame, setCurrentFrame] = useState(0)
  const [fps, setFps] = useState(30)

  // Large file handling states
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [showLargeFileLoader, setShowLargeFileLoader] = useState(false)
  const [serverFilePath, setServerFilePath] = useState('')

  // Visualization options
  const [showKeypoints, setShowKeypoints] = useState(true)
  const [showMask, setShowMask] = useState(true)
  const [showROIs, setShowROIs] = useState(true)
  const [showTrajectory, setShowTrajectory] = useState(true)
  const [showCentroid, setShowCentroid] = useState(true)
  const [showRearingROIs, setShowRearingROIs] = useState(true)

  // Available features in loaded JSON
  const [hasKeypoints, setHasKeypoints] = useState(false)
  const [hasMask, setHasMask] = useState(false)
  const [hasROIs, setHasROIs] = useState(false)
  const [hasRearingAnalysis, setHasRearingAnalysis] = useState(false)

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationFrameRef = useRef<number | null>(null)

  // Handle video file upload
  const handleVideoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Clean up previous video URL if exists
    if (videoUrl) {
      URL.revokeObjectURL(videoUrl)
    }

    // Reset all states
    setVideoFile(file)
    const url = URL.createObjectURL(file)
    setVideoUrl(url)
    setCurrentFrame(0)
    setIsPlaying(false)

    // Reset input to allow same file selection
    e.target.value = ''
  }

  // Handle tracking data sync with video
  const updateSyncStatus = (data: TrackingData) => {
    // Detect available features
    const firstFrame = data.tracking_data?.[0]
    setHasKeypoints(!!firstFrame?.keypoints && firstFrame.keypoints.length > 0)
    setHasMask(!!firstFrame?.mask && firstFrame.mask.length > 0)
    setHasROIs(!!data.rois && data.rois.length > 0)
    setHasRearingAnalysis(!!(data as any).rearing_analysis && !!(data as any).rearing_analysis.rois)
    
    if (data.video_info?.fps) {
      setFps(data.video_info.fps)
    }
  }

  // Handle server file load
  const handleServerFileLoad = async () => {
    if (!serverFilePath.trim()) return

    setIsAnalyzing(true)
    try {
      const response = await analysisApi.loadLargeJson(serverFilePath)
      if (response.data.success && response.data.data) {
        const data = response.data.data as TrackingData
        setTrackingData(data)
        setJsonFileName(serverFilePath.split('/').pop() || 'Server File')
        
        setCurrentFrame(0)
        setIsPlaying(false)
        updateSyncStatus(data)
        
        setShowLargeFileLoader(false)
      } else {
        alert(`Server failed to load JSON: ${response.data.error}`)
      }
    } catch (error: any) {
      alert(`Error loading from server: ${error.message}`)
    } finally {
      setIsAnalyzing(false)
    }
  }

  // Handle JSON file upload
  const handleJsonUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setJsonFileName(file.name)

    const LARGE_FILE_THRESHOLD = 50 * 1024 * 1024 // 50MB

    try {
      let data: TrackingData

      if (file.size > LARGE_FILE_THRESHOLD) {
        // Use server-side upload for large files
        setUploadProgress(0)
        setIsAnalyzing(true)

        const response = await analysisApi.uploadLargeJson(file, (progress) => {
          setUploadProgress(progress)
        })

        setUploadProgress(null)
        setIsAnalyzing(false)

        if (response.data.success && response.data.data) {
          data = response.data.data as TrackingData
        } else {
          throw new Error(response.data.error || 'Server failed to process the file')
        }
      } else {
        // For smaller files, use browser-side parsing
        const reader = new FileReader()
        data = await new Promise((resolve, reject) => {
          reader.onload = (event) => {
            try {
              resolve(JSON.parse(event.target?.result as string))
            } catch (err) {
              reject(err)
            }
          }
          reader.onerror = () => reject(new Error('Failed to read file'))
          reader.readAsText(file)
        })
      }

      // Reset states before loading new data
      setCurrentFrame(0)
      setIsPlaying(false)
      setTrackingData(data)
      updateSyncStatus(data)

    } catch (error: any) {
      console.error('Failed to parse tracking data:', error)
      setUploadProgress(null)
      setIsAnalyzing(false)
      alert('Failed to parse tracking data: ' + error.message)
      
      if (file.size > LARGE_FILE_THRESHOLD) {
        alert('Tip: The server-side upload failed. Try using "Load Large File (Server)" with the full path if the file is already on the server.')
      }
    }

    // Reset input to allow same file selection
    e.target.value = ''
  }

  // Draw ROI
  const drawROI = (ctx: CanvasRenderingContext2D, roi: ROI, index: number) => {
    ctx.strokeStyle = 'rgba(0, 255, 255, 0.8)'
    ctx.lineWidth = 2
    ctx.setLineDash([5, 5])

    if (roi.roi_type === 'Circle') {
      ctx.beginPath()
      ctx.arc(roi.center_x, roi.center_y, roi.radius, 0, 2 * Math.PI)
      ctx.stroke()

      // Draw label
      ctx.fillStyle = 'rgba(0, 255, 255, 0.9)'
      ctx.font = '14px monospace'
      ctx.fillText(`ROI ${index}`, roi.center_x - 20, roi.center_y - roi.radius - 10)
    } else if (roi.roi_type === 'Rectangle') {
      const x = roi.center_x - roi.width / 2
      const y = roi.center_y - roi.height / 2
      ctx.strokeRect(x, y, roi.width, roi.height)

      // Draw label
      ctx.fillStyle = 'rgba(0, 255, 255, 0.9)'
      ctx.font = '14px monospace'
      ctx.fillText(`ROI ${index}`, x, y - 10)
    } else if (roi.roi_type === 'Polygon') {
      ctx.beginPath()
      roi.vertices.forEach(([x, y], i) => {
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.closePath()
      ctx.stroke()

      // Draw label
      ctx.fillStyle = 'rgba(0, 255, 255, 0.9)'
      ctx.font = '14px monospace'
      ctx.fillText(`ROI ${index}`, roi.center_x, roi.center_y - 20)
    }

    ctx.setLineDash([])
  }

  // Handle manual centroid correction
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!trackingData || isPlaying) return

    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video) return

    const rect = canvas.getBoundingClientRect()
    
    // Calculate click position relative to the canvas/video display size
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    
    // Scale coordinates to the actual video dimensions
    const scaleX = video.videoWidth / rect.width
    const scaleY = video.videoHeight / rect.height
    
    const actualX = x * scaleX
    const actualY = y * scaleY

    // Update tracking data in state
    const newData = { ...trackingData }
    if (newData.tracking_data[currentFrame]) {
      newData.tracking_data[currentFrame] = {
        ...newData.tracking_data[currentFrame],
        centroid_x: actualX,
        centroid_y: actualY,
        detection_method: 'manual',
        confidence: 1.0 // Manual is 100% "confident"
      }
      setTrackingData(newData)
    }
  }

  // Draw tracking overlay on canvas
  const drawTrackingOverlay = () => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video || !trackingData) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Set canvas size to match video only if changed
    if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    }

    // Get tracking data for current frame
    const frameData = trackingData.tracking_data?.[currentFrame]
    if (!frameData) return

    // Define colors based on method
    let primaryColor = '#00ff00' // YOLO
    if (frameData.detection_method === 'template') primaryColor = '#ffff00'
    if (frameData.detection_method === 'manual') primaryColor = '#ff9800' // Orange for manual
    if (frameData.detection_method === 'none') primaryColor = '#f44336'

    // Draw ROIs first
    if (showROIs && trackingData.rois && trackingData.rois.length > 0) {
      trackingData.rois.forEach((roi, index) => {
        drawROI(ctx, roi, index)
      })
    }

    // Draw trajectory trail
    if (showTrajectory) {
      const trailLength = 30
      ctx.strokeStyle = 'rgba(255, 100, 100, 0.4)'
      ctx.lineWidth = 2
      ctx.beginPath()

      let started = false
      for (let i = Math.max(0, currentFrame - trailLength); i <= currentFrame; i++) {
        const frame = trackingData.tracking_data?.[i]
        if (frame && frame.detection_method !== 'none') {
          if (!started) {
            ctx.moveTo(frame.centroid_x, frame.centroid_y)
            started = true
          } else {
            ctx.lineTo(frame.centroid_x, frame.centroid_y)
          }
        }
      }
      ctx.stroke()
    }

    // Draw mask (segmentation) - Now uses the primary color of the method
    if (showMask && frameData.mask && frameData.mask.length > 0) {
      ctx.fillStyle = primaryColor + '4D' // 30% alpha
      ctx.strokeStyle = primaryColor
      ctx.lineWidth = 2

      ctx.beginPath()
      frameData.mask.forEach(([x, y], i) => {
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.closePath()
      ctx.fill()
      ctx.stroke()
    }

    // Draw bounding box if detection exists
    if (frameData.detection_method !== 'none' && frameData.bbox) {
      const [x, y, w, h] = frameData.bbox
      ctx.strokeStyle = primaryColor
      ctx.lineWidth = 2
      ctx.strokeRect(x, y, w, h)
    }

    // Draw centroid
    if (showCentroid && frameData.detection_method !== 'none') {
      ctx.fillStyle = primaryColor
      ctx.beginPath()
      ctx.arc(frameData.centroid_x, frameData.centroid_y, 6, 0, 2 * Math.PI)
      ctx.fill()
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 2
      ctx.stroke()
    }

    // Draw keypoints (pose)
    if (showKeypoints && frameData.keypoints && frameData.keypoints.length > 0) {
      frameData.keypoints.forEach((kp, i) => {
        // Draw keypoint
        const alpha = kp.conf
        ctx.fillStyle = `rgba(255, 255, 0, ${alpha})`
        ctx.beginPath()
        ctx.arc(kp.x, kp.y, 6, 0, 2 * Math.PI)
        ctx.fill()

        // Draw keypoint border
        ctx.strokeStyle = `rgba(0, 0, 0, ${alpha})`
        ctx.lineWidth = 2
        ctx.stroke()

        // Draw keypoint index
        ctx.fillStyle = 'white'
        ctx.font = 'bold 10px monospace'
        ctx.fillText(`${i}`, kp.x - 3, kp.y + 4)
      })

      // Draw skeleton connections (common mouse pose connections)
      const connections = [
        [0, 1], [1, 2], [2, 3], [3, 4], // head to body
        [1, 5], [5, 6], // side connections
      ]

      ctx.strokeStyle = 'rgba(255, 255, 0, 0.6)'
      ctx.lineWidth = 2

      connections.forEach(([i, j]) => {
        if (i < frameData.keypoints!.length && j < frameData.keypoints!.length) {
          const kp1 = frameData.keypoints![i]
          const kp2 = frameData.keypoints![j]
          if (kp1.conf > 0.5 && kp2.conf > 0.5) {
            ctx.beginPath()
            ctx.moveTo(kp1.x, kp1.y)
            ctx.lineTo(kp2.x, kp2.y)
            ctx.stroke()
          }
        }
      })
    }

    // Draw rearing ROIs if available
    if (showRearingROIs && (trackingData as any).rearing_analysis?.rois) {
      const rearingROIs = (trackingData as any).rearing_analysis.rois
      rearingROIs.forEach((roi: any) => {
        // Set color based on ROI name
        if (roi.name === 'lower_edge') {
          ctx.strokeStyle = 'rgba(255, 107, 107, 0.8)' // Red
          ctx.fillStyle = 'rgba(255, 107, 107, 0.9)'
        } else if (roi.name === 'upper_edge') {
          ctx.strokeStyle = 'rgba(78, 205, 196, 0.8)' // Teal
          ctx.fillStyle = 'rgba(78, 205, 196, 0.9)'
        } else {
          ctx.strokeStyle = 'rgba(149, 225, 211, 0.8)' // Light teal
          ctx.fillStyle = 'rgba(149, 225, 211, 0.9)'
        }

        ctx.lineWidth = 3
        ctx.setLineDash([5, 5])

        // Draw circle
        ctx.beginPath()
        ctx.arc(roi.center_x, roi.center_y, roi.radius, 0, 2 * Math.PI)
        ctx.stroke()
        ctx.setLineDash([])

        // Draw label
        ctx.font = '14px monospace'
        const label = roi.name.replace('_', ' ').toUpperCase()
        ctx.fillText(label, roi.center_x - 40, roi.center_y - roi.radius - 10)
      })
    }

    // Draw rearing indicator if current frame is rearing
    if ((trackingData as any).rearing_analysis && frameData.rearing) {
      // Draw REARING label in top-right corner
      ctx.fillStyle = 'rgba(255, 0, 0, 0.8)'
      ctx.fillRect(canvas.width - 150, 10, 140, 40)
      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 20px monospace'
      ctx.textAlign = 'right'
      ctx.fillText('REARING', canvas.width - 20, 38)
      ctx.textAlign = 'left' // Reset
    }
  }

  // Update canvas when frame changes
  useEffect(() => {
    if (videoRef.current && trackingData) {
      // Use requestAnimationFrame for smooth rendering
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
      animationFrameRef.current = requestAnimationFrame(() => {
        drawTrackingOverlay()
      })
    }
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [currentFrame, trackingData, videoUrl, showKeypoints, showMask, showROIs, showTrajectory, showCentroid, showRearingROIs])

  // Handle video time update
  const handleTimeUpdate = () => {
    const video = videoRef.current
    if (!video || !trackingData) return

    // Direct frame calculation based on FPS - instant access
    const calculatedFrame = Math.round(video.currentTime * fps)

    // Clamp to valid range
    const maxFrame = (trackingData.video_info?.total_frames || trackingData.tracking_data?.length || 0) - 1
    const frame = Math.max(0, Math.min(calculatedFrame, maxFrame))

    setCurrentFrame(frame)
  }

  // Play/Pause toggle
  const togglePlayPause = () => {
    const video = videoRef.current
    if (!video) return

    if (isPlaying) {
      video.pause()
    } else {
      video.play()
    }
    setIsPlaying(!isPlaying)
  }

  // Skip forward one frame
  const skipForward = () => {
    const video = videoRef.current
    if (!video || !trackingData) return

    const maxFrame = (trackingData.video_info?.total_frames || trackingData.tracking_data?.length || 0) - 1
    if (currentFrame >= maxFrame) return

    video.currentTime = (currentFrame + 1) / fps
  }

  // Skip backward one frame
  const skipBackward = () => {
    const video = videoRef.current
    if (!video || !trackingData) return

    if (currentFrame <= 0) return

    video.currentTime = (currentFrame - 1) / fps
  }

  // Clean up video URL on unmount
  useEffect(() => {
    return () => {
      if (videoUrl) {
        URL.revokeObjectURL(videoUrl)
      }
    }
  }, [videoUrl])

  // Clear all loaded files and reset state
  const handleClearAll = () => {
    // Clean up video URL
    if (videoUrl) {
      URL.revokeObjectURL(videoUrl)
    }

    // Reset all states
    setVideoFile(null)
    setVideoUrl(null)
    setTrackingData(null)
    setIsPlaying(false)
    setCurrentFrame(0)
    setFps(30)
    setHasKeypoints(false)
    setHasMask(false)
    setHasROIs(false)
    setHasRearingAnalysis(false)
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Eye className="w-5 h-5 text-primary-500" />
            View and Fix results
          </h2>
          <div className="flex gap-2">
            {trackingData && (
              <button
                disabled={isDownloading || isAnalyzing}
                onClick={() => {
                  setIsDownloading(true)
                  // Small delay to allow UI to update before heavy JSON processing
                  setTimeout(() => {
                    try {
                      // Remove indentation for large files to save memory (roughly cuts size in half)
                      const isLargeFile = trackingData.tracking_data && trackingData.tracking_data.length > 50000
                      const jsonString = isLargeFile 
                        ? JSON.stringify(trackingData) 
                        : JSON.stringify(trackingData, null, 2)
                        
                      const blob = new Blob([jsonString], { type: 'application/json' })
                      const url = URL.createObjectURL(blob)
                      const link = document.createElement('a')
                      link.href = url
                      link.download = jsonFileName ? jsonFileName.replace('.json', '_fixed.json') : 'results_fixed.json'
                      link.click()
                      URL.revokeObjectURL(url)
                    } catch (error) {
                      console.error('Download error:', error)
                      alert('Error preparing download. The file is too large for the browser to process at once. Try downloading a smaller segment if possible.')
                    } finally {
                      setIsDownloading(false)
                    }
                  }, 100)
                }}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                {isDownloading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Preparing Download...
                  </>
                ) : (
                  'Download Fixed Results'
                )}
              </button>
            )}
            {(videoFile || trackingData) && (
              <button
                onClick={handleClearAll}
                disabled={isDownloading || isAnalyzing || uploadProgress !== null}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                <X className="w-4 h-4" />
                Clear All
              </button>
            )}
          </div>
        </div>

        <p className="text-gray-600 dark:text-gray-400 mb-6">
          Load a video and its corresponding JSON analysis file to visualize tracking results.
        </p>

        {/* File Upload Section */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              <Upload className="w-4 h-4 inline mr-2" />
              Video File
            </label>
            <input
              type="file"
              accept="video/*"
              onChange={handleVideoUpload}
              disabled={isDownloading || isAnalyzing || uploadProgress !== null}
              className="w-full bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2 text-gray-900 dark:text-white file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-600 file:text-white hover:file:bg-primary-700 disabled:opacity-50"
            />
            {videoFile && (
              <p className="text-sm text-green-700 dark:text-green-400 mt-2">✓ {videoFile.name}</p>
            )}
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                <Upload className="w-4 h-4 inline mr-2" />
                JSON File (Tracking Data)
              </label>
              <button
                onClick={() => setShowLargeFileLoader(!showLargeFileLoader)}
                disabled={isDownloading || isAnalyzing}
                className="text-xs text-primary-700 dark:text-primary-400 hover:text-primary-800 dark:hover:text-primary-300 transition-colors disabled:opacity-50"
              >
                {showLargeFileLoader ? 'Standard Upload' : 'Load Large File (Server)'}
              </button>
            </div>

            {showLargeFileLoader ? (
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="Paste full path to JSON file on server..."
                  value={serverFilePath}
                  onChange={(e) => setServerFilePath(e.target.value)}
                  className="w-full bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2 text-gray-900 dark:text-white text-sm"
                />
                <button
                  onClick={handleServerFileLoad}
                  disabled={isAnalyzing || !serverFilePath.trim()}
                  className="w-full bg-primary-600 hover:bg-primary-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:text-gray-500 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {isAnalyzing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading Large JSON...
                    </>
                  ) : 'Load from Disk'}
                </button>
                <p className="text-[10px] text-gray-500 dark:text-gray-400">
                  Tip: Use this for files &gt; 100MB to avoid browser memory errors.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <input
                  type="file"
                  accept=".json"
                  onChange={handleJsonUpload}
                  disabled={isDownloading || isAnalyzing || uploadProgress !== null}
                  className="w-full bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2 text-gray-900 dark:text-white file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-600 file:text-white hover:file:bg-primary-700 disabled:opacity-50"
                />
                {uploadProgress !== null && (
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400">
                      <span>Uploading to server...</span>
                      <span>{Math.round(uploadProgress)}%</span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                      <div
                        className="bg-primary-500 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                )}
                <p className="text-[10px] text-gray-500 dark:text-gray-400">
                  Files &gt; 50MB are automatically processed server-side.
                </p>
              </div>
            )}

            {trackingData && (
              <div className="mt-2 space-y-1">
                <p className="text-sm text-green-700 dark:text-green-400">
                  ✓ {jsonFileName || 'Data Loaded'}
                </p>
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  • JSON: {trackingData.tracking_data?.length || 0} entries
                  {trackingData.video_info?.total_frames && ` (Declared: ${trackingData.video_info.total_frames})`}
                </p>
                <div className="text-xs text-gray-600 dark:text-gray-400">
                  {hasKeypoints && <span className="inline-block mr-3">• Pose detected</span>}
                  {hasMask && <span className="inline-block mr-3">• Segmentation detected</span>}
                  {hasROIs && <span className="inline-block mr-3">• ROIs detected ({trackingData.rois?.length || 0})</span>}
                  {hasRearingAnalysis && <span className="inline-block mr-3 text-orange-700 dark:text-orange-400">• Rearing analysis detected</span>}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Visualization Controls */}
        {trackingData && videoUrl && (
          <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 mb-6 border border-gray-200 dark:border-transparent">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Settings className="w-4 h-4" />
              Visualization Controls
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              <label className="flex items-center gap-2 cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600/30 p-2 rounded transition-colors">
                <input
                  type="checkbox"
                  checked={showCentroid}
                  onChange={(e) => setShowCentroid(e.target.checked)}
                  disabled={isDownloading || isAnalyzing}
                  className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800 disabled:opacity-50"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Centroid</span>
              </label>

              <label
                className={`flex items-center gap-2 p-2 rounded transition-colors ${
                  hasKeypoints && !isDownloading && !isAnalyzing ? 'cursor-pointer hover:bg-gray-600/30' : 'opacity-50 cursor-not-allowed'
                }`}
              >
                <input
                  type="checkbox"
                  checked={showKeypoints}
                  onChange={(e) => setShowKeypoints(e.target.checked)}
                  disabled={!hasKeypoints || isDownloading || isAnalyzing}
                  className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800 disabled:opacity-50"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Pose (Keypoints)</span>
              </label>

              <label
                className={`flex items-center gap-2 p-2 rounded transition-colors ${
                  hasMask && !isDownloading && !isAnalyzing ? 'cursor-pointer hover:bg-gray-600/30' : 'opacity-50 cursor-not-allowed'
                }`}
              >
                <input
                  type="checkbox"
                  checked={showMask}
                  onChange={(e) => setShowMask(e.target.checked)}
                  disabled={!hasMask || isDownloading || isAnalyzing}
                  className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800 disabled:opacity-50"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Mask</span>
              </label>

              <label
                className={`flex items-center gap-2 p-2 rounded transition-colors ${
                  hasROIs && !isDownloading && !isAnalyzing ? 'cursor-pointer hover:bg-gray-600/30' : 'opacity-50 cursor-not-allowed'
                }`}
              >
                <input
                  type="checkbox"
                  checked={showROIs}
                  onChange={(e) => setShowROIs(e.target.checked)}
                  disabled={!hasROIs || isDownloading || isAnalyzing}
                  className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800 disabled:opacity-50"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">ROIs</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600/30 p-2 rounded transition-colors">
                <input
                  type="checkbox"
                  checked={showTrajectory}
                  onChange={(e) => setShowTrajectory(e.target.checked)}
                  disabled={isDownloading || isAnalyzing}
                  className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800 disabled:opacity-50"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Trajectory</span>
              </label>

              <label
                className={`flex items-center gap-2 p-2 rounded transition-colors ${
                  hasRearingAnalysis && !isDownloading && !isAnalyzing ? 'cursor-pointer hover:bg-gray-600/30' : 'opacity-50 cursor-not-allowed'
                }`}
              >
                <input
                  type="checkbox"
                  checked={showRearingROIs}
                  onChange={(e) => setShowRearingROIs(e.target.checked)}
                  disabled={!hasRearingAnalysis || isDownloading || isAnalyzing}
                  className="w-4 h-4 rounded border-gray-600 text-primary-600 focus:ring-primary-500 focus:ring-offset-gray-800 disabled:opacity-50"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Rearing ROIs</span>
              </label>
            </div>
          </div>
        )}

        {/* Video Player Section */}
        {videoUrl && (
          <div className="space-y-4">
            <div className="bg-black rounded-lg overflow-hidden border border-gray-300 dark:border-gray-700 relative">
              <div className="relative" style={{ width: '100%', aspectRatio: '16/9' }}>
                <video
                  ref={videoRef}
                  src={videoUrl}
                  onTimeUpdate={handleTimeUpdate}
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                  className="w-full h-full object-contain"
                  style={{ position: 'absolute', top: 0, left: 0 }}
                />
                <canvas
                  ref={canvasRef}
                  onClick={handleCanvasClick}
                  className={`w-full h-full object-contain ${!isPlaying && trackingData ? 'cursor-crosshair' : ''}`}
                  style={{ position: 'absolute', top: 0, left: 0 }}
                />
              </div>
              {!isPlaying && trackingData && (
                <div className="absolute top-4 left-4 bg-primary-600/80 text-white text-xs px-2 py-1 rounded-md backdrop-blur-sm pointer-events-none">
                  Click to manually fix centroid
                </div>
              )}
            </div>

            {/* Video Controls */}
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
              <div className="flex items-center justify-center gap-2 mb-4">
                <button
                  onClick={skipBackward}
                  className="px-4 py-2 bg-gray-300 hover:bg-gray-400 dark:bg-gray-600 dark:hover:bg-gray-500 text-gray-900 dark:text-gray-100 rounded-lg transition-colors flex items-center gap-2 text-sm"
                  title="Previous frame"
                >
                  <SkipBack className="w-4 h-4" />
                  <span>Previous Frame</span>
                </button>

                <div className="mx-2 flex items-center gap-2">
                  <button
                    onClick={togglePlayPause}
                    className="p-3 bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors"
                  >
                    {isPlaying ? (
                      <Pause className="w-6 h-6" />
                    ) : (
                      <Play className="w-6 h-6" />
                    )}
                  </button>
                </div>

                <button
                  onClick={skipForward}
                  className="px-4 py-2 bg-gray-300 hover:bg-gray-400 dark:bg-gray-600 dark:hover:bg-gray-500 text-gray-900 dark:text-gray-100 rounded-lg transition-colors flex items-center gap-2 text-sm"
                  title="Next frame"
                >
                  <span>Next Frame</span>
                  <SkipForward className="w-4 h-4" />
                </button>
              </div>

              {/* Frame Info */}
              <div className="text-center text-sm text-gray-700 dark:text-gray-300">
                <span className="font-mono">
                  Frame: {currentFrame} / {trackingData?.video_info?.total_frames || '?'}
                </span>
                <span className="mx-3 text-gray-400 dark:text-gray-500">|</span>
                <span className="font-mono">
                  Time: {videoRef.current?.currentTime.toFixed(2)}s
                </span>
                <span className="mx-3 text-gray-400 dark:text-gray-500">|</span>
                <span className="font-mono">FPS: {fps}</span>
              </div>

              {/* Timeline Slider */}
              {videoRef.current && (
                <input
                  type="range"
                  min="0"
                  max={videoRef.current.duration || 0}
                  step="0.01"
                  value={videoRef.current.currentTime || 0}
                  disabled={isDownloading || isAnalyzing || uploadProgress !== null}
                  onChange={(e) => {
                    if (videoRef.current) {
                      videoRef.current.currentTime = parseFloat(e.target.value)
                    }
                  }}
                  className="w-full mt-4 disabled:opacity-50"
                />
              )}
            </div>
          </div>
        )}

        {/* Instructions when no files loaded */}
        {!videoUrl && !trackingData && (
          <div className="bg-gray-50 dark:bg-gray-700/30 rounded-lg p-8 text-center border border-gray-300 dark:border-gray-600 border-dashed">
            <Eye className="w-16 h-16 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-700 dark:text-gray-300 mb-2">
              No files loaded
            </h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              Load a video and a JSON analysis file to start visualization
            </p>
          </div>
        )}
      </div>

      {/* Statistics Panel */}
      {trackingData && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Analysis Statistics</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
              <div className="text-sm text-gray-600 dark:text-gray-400">Total Frames</div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {trackingData.video_info?.total_frames || 0}
              </div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
              <div className="text-sm text-gray-600 dark:text-gray-400">YOLO Detections</div>
              <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                {trackingData.statistics?.yolo_detections || 0}
              </div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
              <div className="text-sm text-gray-600 dark:text-gray-400">Template Detections</div>
              <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
                {trackingData.statistics?.template_detections || 0}
              </div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
              <div className="text-sm text-gray-600 dark:text-gray-400">Missed Frames</div>
              <div className="text-2xl font-bold text-red-600 dark:text-red-400">
                {trackingData.statistics?.frames_without_detection || 0}
              </div>
            </div>
          </div>

          {/* Rearing Analysis Statistics */}
          {(trackingData as any).rearing_analysis && (
            <div className="mt-6">
              <h4 className="text-md font-semibold mb-3 text-primary-700 dark:text-primary-400">Rearing Analysis</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
                  <div className="text-sm text-gray-600 dark:text-gray-400">Total Events</div>
                  <div className="text-2xl font-bold text-orange-600 dark:text-orange-400">
                    {(trackingData as any).rearing_analysis.statistics?.total_events || 0}
                  </div>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
                  <div className="text-sm text-gray-600 dark:text-gray-400">Total Duration</div>
                  <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                    {(trackingData as any).rearing_analysis.statistics?.total_duration_seconds?.toFixed(1) || 0}s
                  </div>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
                  <div className="text-sm text-gray-600 dark:text-gray-400">Avg Duration</div>
                  <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {(trackingData as any).rearing_analysis.statistics?.average_duration_seconds?.toFixed(2) || 0}s
                  </div>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-transparent">
                  <div className="text-sm text-gray-600 dark:text-gray-400">Analysis Type</div>
                  <div className="text-lg font-bold text-cyan-600 dark:text-cyan-400 uppercase">
                    {(trackingData as any).rearing_analysis.analysis_type || 'N/A'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Current Frame Details */}
          {trackingData.tracking_data?.[currentFrame] && (
            <div className="mt-4 bg-gray-50 dark:bg-gray-700/30 rounded-lg p-4 border border-gray-200 dark:border-transparent">
              <h4 className="font-medium text-gray-700 dark:text-gray-300 mb-2">
                Current Frame ({currentFrame})
                {videoRef.current && (
                  <span className="text-xs text-gray-500 dark:text-gray-500 ml-3">
                    Vídeo: {videoRef.current.currentTime.toFixed(3)}s |
                    JSON: {trackingData.tracking_data[currentFrame].timestamp_sec.toFixed(3)}s |
                    Diff: {Math.abs(videoRef.current.currentTime - trackingData.tracking_data[currentFrame].timestamp_sec).toFixed(3)}s
                  </span>
                )}
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm font-mono">
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Method:</span>{' '}
                  <span className="text-gray-900 dark:text-white">
                    {trackingData.tracking_data[currentFrame].detection_method}
                  </span>
                </div>
                {trackingData.tracking_data[currentFrame].confidence !== undefined && (
                  <div>
                    <span className="text-gray-600 dark:text-gray-400">Confidence:</span>{' '}
                    <span className="text-gray-900 dark:text-white">
                      {(trackingData.tracking_data[currentFrame].confidence! * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-gray-600 dark:text-gray-400">Centroid:</span>{' '}
                  <span className="text-gray-900 dark:text-white">
                    ({Math.round(trackingData.tracking_data[currentFrame].centroid_x)},
                     {Math.round(trackingData.tracking_data[currentFrame].centroid_y)})
                  </span>
                </div>
                {trackingData.tracking_data[currentFrame].roi && (
                  <div>
                    <span className="text-gray-600 dark:text-gray-400">ROI:</span>{' '}
                    <span className="text-gray-900 dark:text-white">
                      {trackingData.tracking_data[currentFrame].roi}
                    </span>
                  </div>
                )}
                {trackingData.tracking_data[currentFrame].keypoints && (
                  <div>
                    <span className="text-gray-600 dark:text-gray-400">Keypoints:</span>{' '}
                    <span className="text-gray-900 dark:text-white">
                      {trackingData.tracking_data[currentFrame].keypoints!.length} points
                    </span>
                  </div>
                )}
                {trackingData.tracking_data[currentFrame].mask && (
                  <div>
                    <span className="text-gray-600 dark:text-gray-400">Mask:</span>{' '}
                    <span className="text-gray-900 dark:text-white">
                      {trackingData.tracking_data[currentFrame].mask!.length} points
                    </span>
                  </div>
                )}
                {(trackingData.tracking_data[currentFrame] as any).rearing !== undefined && (
                  <div>
                    <span className="text-gray-600 dark:text-gray-400">Rearing:</span>{' '}
                    <span className={(trackingData.tracking_data[currentFrame] as any).rearing ? 'text-red-600 dark:text-red-400 font-bold' : 'text-green-700 dark:text-green-400'}>
                      {(trackingData.tracking_data[currentFrame] as any).rearing ? 'TRUE' : 'FALSE'}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      {trackingData && videoUrl && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Legend</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 border-2 border-green-500"></div>
              <span className="text-sm text-gray-700 dark:text-gray-300">YOLO Detection / Centroid</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 border-2 border-yellow-500"></div>
              <span className="text-sm text-gray-700 dark:text-gray-300">Template Detection</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 bg-red-500/60"></div>
              <span className="text-sm text-gray-700 dark:text-gray-300">Trajectory (last 30 frames)</span>
            </div>
            {hasKeypoints && (
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 bg-yellow-400 rounded-full"></div>
                <span className="text-sm text-gray-700 dark:text-gray-300">Keypoints (Pose)</span>
              </div>
            )}
            {hasMask && (
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 bg-pink-500/60 border border-pink-500"></div>
                <span className="text-sm text-gray-700 dark:text-gray-300">Mask (Segmentation)</span>
              </div>
            )}
            {hasROIs && (
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 border-2 border-cyan-400 border-dashed"></div>
                <span className="text-sm text-gray-700 dark:text-gray-300">ROIs</span>
              </div>
            )}
            {hasRearingAnalysis && (
              <>
                <div className="flex items-center gap-3">
                  <div className="w-4 h-4 border-2 border-red-400 border-dashed"></div>
                  <span className="text-sm text-gray-700 dark:text-gray-300">Lower Edge (Rearing)</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-4 h-4 border-2 border-teal-400 border-dashed"></div>
                  <span className="text-sm text-gray-700 dark:text-gray-300">Upper Edge (Rearing)</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-4 h-4 bg-red-600"></div>
                  <span className="text-sm text-gray-700 dark:text-gray-300">Rearing Indicator</span>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
