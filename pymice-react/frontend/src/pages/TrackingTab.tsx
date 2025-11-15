import { useState, useRef, useEffect } from 'react'
import { Upload, Play, Pause, Square, Download, Settings } from 'lucide-react'
import type { ROI, ROIPreset, ROIType } from '@/types'
import { drawROI } from '@/utils/canvas'

export default function TrackingTab() {
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [modelFile, setModelFile] = useState<string>('')
  const [rois, setRois] = useState<ROI[]>([])
  const [currentROIType, setCurrentROIType] = useState<ROIType>('Rectangle')
  const [isTracking, setIsTracking] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [progress, setProgress] = useState(0)
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5)
  const [iouThreshold, setIouThreshold] = useState(0.45)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null)
  const [polygonPoints, setPolygonPoints] = useState<{ x: number; y: number }[]>([])
  const [currentMousePos, setCurrentMousePos] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    if (videoFile && videoRef.current) {
      const video = videoRef.current
      video.src = URL.createObjectURL(videoFile)

      video.onloadedmetadata = () => {
        // Set canvas size to match video aspect ratio
        const canvas = canvasRef.current
        if (canvas && video.videoWidth && video.videoHeight) {
          const maxDisplayWidth = 1200
          const maxDisplayHeight = 600
          const aspectRatio = video.videoWidth / video.videoHeight

          let displayWidth = maxDisplayWidth
          let displayHeight = maxDisplayWidth / aspectRatio

          if (displayHeight > maxDisplayHeight) {
            displayHeight = maxDisplayHeight
            displayWidth = maxDisplayHeight * aspectRatio
          }

          canvas.style.width = `${displayWidth}px`
          canvas.style.height = `${displayHeight}px`
        }

        // Seek to first frame and pause
        video.currentTime = 0
      }

      video.onseeked = () => {
        // Draw frame after seeking is complete
        video.pause()
        requestAnimationFrame(() => {
          drawFrame()
        })
      }
    }
  }, [videoFile])

  useEffect(() => {
    drawFrame()
  }, [rois])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && currentROIType === 'Polygon' && polygonPoints.length > 0) {
        // Cancel polygon drawing
        setPolygonPoints([])
        setCurrentMousePos(null)
        drawFrame()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentROIType, polygonPoints])

  const drawFrame = () => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width = video.videoWidth || 640
    canvas.height = video.videoHeight || 480

    // Draw video frame
    if (video.readyState >= 2) {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    }

    // Draw ROIs
    rois.forEach((roi, index) => {
      const colors = ['#00ff00', '#ff00ff', '#00ffff', '#ffff00', '#ff8800']
      drawROI(ctx, roi, colors[index % colors.length], 2, true, 0.1)
    })
  }

  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const x = (e.clientX - rect.left) * scaleX
    const y = (e.clientY - rect.top) * scaleY

    // Polygon mode: click to add points
    if (currentROIType === 'Polygon') {
      // Check if clicking near first point to close polygon (within 10 pixels)
      if (polygonPoints.length >= 3) {
        const firstPoint = polygonPoints[0]
        const distance = Math.sqrt(
          Math.pow(x - firstPoint.x, 2) + Math.pow(y - firstPoint.y, 2)
        )
        if (distance < 10) {
          // Close polygon
          const newROI: ROI = {
            roi_type: 'Polygon',
            vertices: polygonPoints.map(p => [p.x, p.y]),
          }
          setRois([...rois, newROI])
          setPolygonPoints([])
          setCurrentMousePos(null)
          return
        }
      }

      // Add point to polygon
      setPolygonPoints([...polygonPoints, { x, y }])
    } else {
      // Rectangle or Circle mode: start dragging
      setIsDrawing(true)
      setDrawStart({ x, y })
    }
  }

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const x = (e.clientX - rect.left) * scaleX
    const y = (e.clientY - rect.top) * scaleY

    // Update current mouse position for polygon preview
    setCurrentMousePos({ x, y })

    // Only redraw for non-polygon modes when dragging
    if (currentROIType !== 'Polygon' && (!isDrawing || !drawStart)) return

    // Redraw frame
    drawFrame()

    // Draw preview of current ROI
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 2
    ctx.setLineDash([5, 5])

    if (currentROIType === 'Rectangle' && isDrawing && drawStart) {
      const width = x - drawStart.x
      const height = y - drawStart.y
      ctx.strokeRect(drawStart.x, drawStart.y, width, height)
    } else if (currentROIType === 'Circle' && isDrawing && drawStart) {
      const radius = Math.sqrt(
        Math.pow(x - drawStart.x, 2) + Math.pow(y - drawStart.y, 2)
      )
      ctx.beginPath()
      ctx.arc(drawStart.x, drawStart.y, radius, 0, 2 * Math.PI)
      ctx.stroke()
    } else if (currentROIType === 'Polygon' && polygonPoints.length > 0) {
      // Draw polygon preview
      ctx.beginPath()
      ctx.moveTo(polygonPoints[0].x, polygonPoints[0].y)
      for (let i = 1; i < polygonPoints.length; i++) {
        ctx.lineTo(polygonPoints[i].x, polygonPoints[i].y)
      }
      // Draw line to current mouse position
      ctx.lineTo(x, y)
      // Draw line back to first point if we have at least 3 points
      if (polygonPoints.length >= 3) {
        ctx.lineTo(polygonPoints[0].x, polygonPoints[0].y)
      }
      ctx.stroke()

      // Draw points
      ctx.setLineDash([])
      ctx.fillStyle = '#ffffff'
      polygonPoints.forEach(point => {
        ctx.beginPath()
        ctx.arc(point.x, point.y, 5, 0, 2 * Math.PI)
        ctx.fill()
      })
      // Highlight first point if we can close
      if (polygonPoints.length >= 3) {
        ctx.fillStyle = '#00ff00'
        ctx.beginPath()
        ctx.arc(polygonPoints[0].x, polygonPoints[0].y, 7, 0, 2 * Math.PI)
        ctx.fill()
      }
    }

    ctx.setLineDash([])
  }

  const handleCanvasMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (currentROIType === 'Polygon') return // Polygon uses click, not drag

    if (!isDrawing || !drawStart) return

    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const x = (e.clientX - rect.left) * scaleX
    const y = (e.clientY - rect.top) * scaleY

    let newROI: ROI | null = null

    if (currentROIType === 'Rectangle') {
      const width = Math.abs(x - drawStart.x)
      const height = Math.abs(y - drawStart.y)
      const centerX = (drawStart.x + x) / 2
      const centerY = (drawStart.y + y) / 2

      newROI = {
        roi_type: 'Rectangle',
        center_x: centerX,
        center_y: centerY,
        width,
        height,
      }
    } else if (currentROIType === 'Circle') {
      const radius = Math.sqrt(
        Math.pow(x - drawStart.x, 2) + Math.pow(y - drawStart.y, 2)
      )

      newROI = {
        roi_type: 'Circle',
        center_x: drawStart.x,
        center_y: drawStart.y,
        radius,
      }
    }

    if (newROI) {
      setRois([...rois, newROI])
    }

    setIsDrawing(false)
    setDrawStart(null)
  }

  const handleStartTracking = () => {
    setIsTracking(true)
    setIsPaused(false)
    // Simulate progress
    let p = 0
    const interval = setInterval(() => {
      p += 1
      setProgress(p)
      if (p >= 100) {
        clearInterval(interval)
        setIsTracking(false)
      }
    }, 100)
  }

  const handlePauseTracking = () => {
    setIsPaused(!isPaused)
  }

  const handleStopTracking = () => {
    setIsTracking(false)
    setIsPaused(false)
    setProgress(0)
  }

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-semibold mb-4">Tracking Configuration</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
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
              YOLO Model
            </label>
            <select
              value={modelFile}
              onChange={(e) => setModelFile(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            >
              <option value="">Select model...</option>
              <option value="yolov11n.pt">YOLOv11n (nano)</option>
              <option value="yolov11s.pt">YOLOv11s (small)</option>
              <option value="yolov11m.pt">YOLOv11m (medium)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              ROI Type
            </label>
            <select
              value={currentROIType}
              onChange={(e) => setCurrentROIType(e.target.value as ROIType)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            >
              <option value="Rectangle">Rectangle</option>
              <option value="Circle">Circle</option>
              <option value="Polygon">Polygon</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Confidence Threshold: {confidenceThreshold.toFixed(2)}
            </label>
            <input
              type="range"
              min="0.1"
              max="0.9"
              step="0.05"
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
              className="w-full"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              IOU Threshold: {iouThreshold.toFixed(2)}
            </label>
            <input
              type="range"
              min="0.1"
              max="0.9"
              step="0.05"
              value={iouThreshold}
              onChange={(e) => setIouThreshold(parseFloat(e.target.value))}
              className="w-full"
            />
          </div>
        </div>

        <div className="flex gap-4 items-center">
          <button
            onClick={handleStartTracking}
            disabled={!videoFile || !modelFile || isTracking}
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Play className="w-5 h-5" />
            Start Tracking
          </button>

          {isTracking && (
            <>
              <button
                onClick={handlePauseTracking}
                className="px-6 py-3 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                <Pause className="w-5 h-5" />
                {isPaused ? 'Resume' : 'Pause'}
              </button>

              <button
                onClick={handleStopTracking}
                className="px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                <Square className="w-5 h-5" />
                Stop
              </button>

              <div className="flex-1">
                <div className="bg-gray-700 rounded-full h-3 overflow-hidden">
                  <div
                    className="bg-primary-500 h-full transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className="text-sm text-gray-400 mt-1">{progress}% completed</div>
              </div>
            </>
          )}

          <button className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2">
            <Download className="w-5 h-5" />
            Download Results
          </button>
        </div>
      </div>

      {/* Video Canvas */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Video Preview & ROI Drawing</h3>
        <div className="bg-black rounded-lg overflow-hidden border border-gray-700 relative flex items-center justify-center" style={{ minHeight: '400px' }}>
          <video ref={videoRef} className="hidden" />
          <canvas
            ref={canvasRef}
            className="max-w-full cursor-crosshair"
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            onMouseLeave={() => setIsDrawing(false)}
          />
          <div className="absolute top-4 right-4 bg-black/70 px-3 py-2 rounded-lg text-sm">
            {currentROIType === 'Polygon' ? (
              polygonPoints.length === 0 ? (
                'Click to add polygon points'
              ) : polygonPoints.length < 3 ? (
                `Click to add more points (${polygonPoints.length} points)`
              ) : (
                'Click green point to close, or ESC to cancel'
              )
            ) : (
              `Click and drag to draw ${currentROIType}`
            )}
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            onClick={() => setRois([])}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm"
          >
            Clear All ROIs
          </button>
          <div className="text-sm text-gray-400 flex items-center">
            Total ROIs: {rois.length}
          </div>
        </div>
      </div>
    </div>
  )
}
