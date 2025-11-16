import { useState, useRef, useEffect } from 'react'
import { Upload, Play, Square, Download, Settings } from 'lucide-react'
import type { ROI, ROIPreset, ROIType } from '@/types'
import { drawROI } from '@/utils/canvas'
import { videoApi, trackingApi } from '@/services/api'

export default function TrackingTab() {
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [uploadedFilename, setUploadedFilename] = useState<string>('')
  const [modelFile, setModelFile] = useState<string>('')
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [rois, setRois] = useState<ROI[]>([])
  const [currentROIType, setCurrentROIType] = useState<ROIType>('Rectangle')
  const [isTracking, setIsTracking] = useState(false)
  const [progress, setProgress] = useState(0)
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.25)
  const [iouThreshold, setIouThreshold] = useState(0.45)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [trackingFrameUrl, setTrackingFrameUrl] = useState<string>('')
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const trackingIntervalRef = useRef<number | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null)
  const [polygonPoints, setPolygonPoints] = useState<{ x: number; y: number }[]>([])
  const [currentMousePos, setCurrentMousePos] = useState<{ x: number; y: number } | null>(null)
  const [trackingLogs, setTrackingLogs] = useState<Array<{ time: string; message: string }>>([])
  const logsEndRef = useRef<HTMLDivElement>(null)
  const [roiTemplates, setRoiTemplates] = useState<Array<{
    filename: string
    preset_name: string
    description: string
    timestamp: string
    roi_count: number
  }>>([])
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [showSaveTemplateModal, setShowSaveTemplateModal] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [templateDescription, setTemplateDescription] = useState('')

  useEffect(() => {
    loadModels()
    loadTemplates()
  }, [])

  useEffect(() => {
    // Auto-scroll to latest log
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [trackingLogs])

  const addLog = (message: string) => {
    const time = new Date().toLocaleTimeString()
    setTrackingLogs(prev => [...prev, { time, message }])
  }

  const loadModels = async () => {
    try {
      const response = await trackingApi.listModels()
      if (response.data.success && response.data.data) {
        const models = response.data.data.models || []
        setAvailableModels(models)
        if (models.length > 0) {
          setModelFile(models[0])
        }
      }
    } catch (error) {
      console.error('Failed to load models:', error)
    }
  }

  const loadTemplates = async () => {
    try {
      const response = await trackingApi.listROITemplates()
      if (response.data.success && response.data.data) {
        setRoiTemplates(response.data.data.templates || [])
      }
    } catch (error) {
      console.error('Failed to load templates:', error)
    }
  }

  const handleSaveTemplate = async () => {
    if (!templateName.trim() || rois.length === 0) {
      addLog('✗ Please enter a template name and draw at least one ROI')
      return
    }

    try {
      const video = videoRef.current
      const frameWidth = video?.videoWidth || 640
      const frameHeight = video?.videoHeight || 480

      // Prepare ROIs with center coordinates
      const preparedRois = rois.map(roi => {
        if (roi.roi_type === 'Polygon') {
          const vertices = roi.vertices || []
          const sumX = vertices.reduce((sum, v) => sum + v[0], 0)
          const sumY = vertices.reduce((sum, v) => sum + v[1], 0)
          return {
            ...roi,
            center_x: sumX / vertices.length,
            center_y: sumY / vertices.length,
          }
        }
        return roi
      })

      await trackingApi.saveROITemplate({
        preset_name: templateName,
        description: templateDescription,
        timestamp: new Date().toISOString(),
        frame_width: frameWidth,
        frame_height: frameHeight,
        rois: preparedRois,
      })

      addLog(`✓ Template "${templateName}" saved successfully`)
      setShowSaveTemplateModal(false)
      setTemplateName('')
      setTemplateDescription('')
      loadTemplates()
    } catch (error) {
      console.error('Failed to save template:', error)
      addLog('✗ Failed to save template: ' + (error as Error).message)
    }
  }

  const handleLoadTemplate = async () => {
    if (!selectedTemplate) return

    try {
      const response = await trackingApi.loadROITemplate(selectedTemplate)
      if (response.data.success && response.data.data) {
        setRois(response.data.data.rois || [])
        drawFrame()
        addLog(`✓ Template "${response.data.data.preset_name}" loaded successfully`)
      }
    } catch (error) {
      console.error('Failed to load template:', error)
      addLog('✗ Failed to load template: ' + (error as Error).message)
    }
  }

  const handleDeleteTemplate = async (filename: string) => {
    if (!confirm('Are you sure you want to delete this template?')) return

    try {
      await trackingApi.deleteROITemplate(filename)
      addLog('✓ Template deleted successfully')
      setSelectedTemplate('')
      loadTemplates()
    } catch (error) {
      console.error('Failed to delete template:', error)
      addLog('✗ Failed to delete template: ' + (error as Error).message)
    }
  }

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

  const handleStartTracking = async () => {
    if (!videoFile || !modelFile) return

    try {
      setIsUploading(true)

      // Upload video if not already uploaded
      let filename = uploadedFilename
      if (!filename) {
        const uploadResponse = await videoApi.upload(videoFile)
        if (uploadResponse.data.success && uploadResponse.data.data) {
          filename = uploadResponse.data.data.filename
          setUploadedFilename(filename)
        } else {
          throw new Error('Failed to upload video')
        }
      }

      setIsUploading(false)
      setIsTracking(true)
      setProgress(0)

      // Get video dimensions from the video element
      const video = videoRef.current
      const frameWidth = video?.videoWidth || 640
      const frameHeight = video?.videoHeight || 480

      // Prepare ROIs with required fields
      const preparedRois = rois.map(roi => {
        if (roi.roi_type === 'Polygon') {
          // Calculate center for polygon
          const vertices = roi.vertices || []
          const sumX = vertices.reduce((sum, v) => sum + v[0], 0)
          const sumY = vertices.reduce((sum, v) => sum + v[1], 0)
          const centerX = sumX / vertices.length
          const centerY = sumY / vertices.length
          return {
            ...roi,
            center_x: centerX,
            center_y: centerY,
          }
        }
        return roi
      })

      // Start tracking
      const trackingResponse = await trackingApi.startTracking({
        video_filename: filename,
        model_name: modelFile,
        rois: {
          preset_name: 'custom',
          description: 'Custom ROI configuration',
          timestamp: new Date().toISOString(),
          frame_width: frameWidth,
          frame_height: frameHeight,
          rois: preparedRois,
        },
        confidence_threshold: confidenceThreshold,
        iou_threshold: iouThreshold,
      })

      if (trackingResponse.data.success && trackingResponse.data.data) {
        const newTaskId = trackingResponse.data.data.task_id
        setTaskId(newTaskId)
        addLog('Tracking started successfully')

        // Poll for progress and frames
        const interval = setInterval(async () => {
          try {
            const progressResponse = await trackingApi.getProgress(newTaskId)
            if (progressResponse.data.success && progressResponse.data.data) {
              const progressData = progressResponse.data.data
              setProgress(progressData.percentage || 0)

              // Update tracking frame URL for live preview
              setTrackingFrameUrl(`/api/tracking/frame/${newTaskId}?t=${Date.now()}`)

              if (progressData.status === 'completed') {
                clearInterval(interval)
                setIsTracking(false)
                // Keep the last frame visible - don't clear trackingFrameUrl
                addLog('✓ Tracking completed! You can now download the results.')
              } else if (progressData.status === 'error') {
                clearInterval(interval)
                setIsTracking(false)
                setTrackingFrameUrl('')
                addLog('✗ Tracking failed: ' + progressData.error)
              }
            }
          } catch (error) {
            console.error('Failed to get progress:', error)
          }
        }, 500) // Poll every 500ms for smoother updates

        trackingIntervalRef.current = interval
      }
    } catch (error) {
      console.error('Failed to start tracking:', error)
      addLog('✗ Failed to start tracking: ' + (error as Error).message)
      setIsTracking(false)
      setIsUploading(false)
    }
  }

  const handleStopTracking = async () => {
    if (taskId) {
      try {
        await trackingApi.stopTracking(taskId)
        addLog('Tracking stopped by user')
      } catch (error) {
        console.error('Failed to stop tracking:', error)
      }
    }
    if (trackingIntervalRef.current) {
      clearInterval(trackingIntervalRef.current)
      trackingIntervalRef.current = null
    }
    setIsTracking(false)
    setProgress(0)
    setTrackingFrameUrl('')
  }

  const handleDownloadResults = async () => {
    if (!taskId) return

    try {
      const response = await trackingApi.downloadResults(taskId)
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `tracking_results_${taskId}.json`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      addLog('✓ Results downloaded successfully')
    } catch (error) {
      console.error('Failed to download results:', error)
      addLog('✗ Failed to download results: ' + (error as Error).message)
    }
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
              YOLO Model {availableModels.length === 0 && <span className="text-red-400">(No models found)</span>}
            </label>
            <select
              value={modelFile}
              onChange={(e) => setModelFile(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              disabled={availableModels.length === 0}
            >
              <option value="">Select model...</option>
              {availableModels.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
            {availableModels.length === 0 && (
              <p className="text-xs text-gray-400 mt-1">
                Place .pt model files in backend/temp/models/ directory
              </p>
            )}
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

        {/* ROI Templates Section */}
        <div className="bg-gray-700/30 rounded-lg p-4 mb-4">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">ROI Templates</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Load Template
              </label>
              <select
                value={selectedTemplate}
                onChange={(e) => setSelectedTemplate(e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              >
                <option value="">Select a template...</option>
                {roiTemplates.map((template) => (
                  <option key={template.filename} value={template.filename}>
                    {template.preset_name} ({template.roi_count} ROIs)
                  </option>
                ))}
              </select>
            </div>
            <div className="flex gap-2 items-end">
              <button
                onClick={handleLoadTemplate}
                disabled={!selectedTemplate}
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg text-sm font-medium"
              >
                Load
              </button>
              <button
                onClick={() => selectedTemplate && handleDeleteTemplate(selectedTemplate)}
                disabled={!selectedTemplate}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg text-sm font-medium"
              >
                Delete
              </button>
            </div>
          </div>
          <div className="mt-3">
            <button
              onClick={() => setShowSaveTemplateModal(true)}
              disabled={rois.length === 0}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg text-sm font-medium"
            >
              Save Current ROIs as Template
            </button>
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
            disabled={!videoFile || !modelFile || isTracking || isUploading}
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Play className="w-5 h-5" />
            {isUploading ? 'Uploading...' : 'Start Tracking'}
          </button>

          {isTracking && (
            <>
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
                <div className="text-sm text-gray-400 mt-1">{progress.toFixed(1)}% completed</div>
              </div>
            </>
          )}

          <button
            onClick={handleDownloadResults}
            disabled={!taskId || isTracking}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Download className="w-5 h-5" />
            Download Results
          </button>
        </div>
      </div>

      {/* Video Canvas */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">
          {isTracking ? 'Live Tracking Preview' : trackingFrameUrl ? 'Tracking Result' : 'Video Preview & ROI Drawing'}
        </h3>
        <div className="bg-black rounded-lg overflow-hidden border border-gray-700 relative flex items-center justify-center" style={{ minHeight: '400px' }}>
          <video ref={videoRef} className="hidden" />

          {/* Show tracking frame when tracking is active or when last frame is available */}
          {trackingFrameUrl && (
            <img
              src={trackingFrameUrl}
              alt="Tracking preview"
              className="max-w-full max-h-[600px] w-auto h-auto"
              style={{ objectFit: 'contain' }}
            />
          )}

          {/* Show canvas for ROI drawing when not tracking and no tracking frame */}
          {!isTracking && !trackingFrameUrl && (
            <canvas
              ref={canvasRef}
              className="max-w-full cursor-crosshair"
              onMouseDown={handleCanvasMouseDown}
              onMouseMove={handleCanvasMouseMove}
              onMouseUp={handleCanvasMouseUp}
              onMouseLeave={() => setIsDrawing(false)}
            />
          )}

          {!isTracking && !trackingFrameUrl && (
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
          )}
        </div>

        <div className="mt-4 flex gap-2">
          {trackingFrameUrl && !isTracking && (
            <button
              onClick={() => {
                setTrackingFrameUrl('')
                setTaskId(null)
                setProgress(0)
              }}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
            >
              New Tracking
            </button>
          )}
          {!trackingFrameUrl && (
            <>
              <button
                onClick={() => setRois([])}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm"
              >
                Clear All ROIs
              </button>
              <div className="text-sm text-gray-400 flex items-center">
                Total ROIs: {rois.length}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Tracking Logs */}
      {trackingLogs.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Tracking Log</h3>
          <div className="bg-black rounded-lg p-4 border border-gray-700 max-h-48 overflow-y-auto font-mono text-sm">
            {trackingLogs.map((log, index) => (
              <div key={index} className="text-gray-300 mb-1">
                <span className="text-gray-500">[{log.time}]</span> {log.message}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}

      {/* Save Template Modal */}
      {showSaveTemplateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 border border-gray-700">
            <h3 className="text-xl font-semibold mb-4">Save ROI Template</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Template Name *
                </label>
                <input
                  type="text"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="e.g., Open Field Test, Y-Maze, etc."
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Description (optional)
                </label>
                <textarea
                  value={templateDescription}
                  onChange={(e) => setTemplateDescription(e.target.value)}
                  placeholder="Brief description of the experiment setup..."
                  rows={3}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div className="text-sm text-gray-400">
                {rois.length} ROI(s) will be saved
              </div>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => {
                    setShowSaveTemplateModal(false)
                    setTemplateName('')
                    setTemplateDescription('')
                  }}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveTemplate}
                  disabled={!templateName.trim()}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg"
                >
                  Save Template
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
