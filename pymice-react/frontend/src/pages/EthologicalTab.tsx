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
  const [videoInfo, setVideoInfo] = useState<{ frames: number; duration: number; fps: number } | null>(null)
  const [jsonFileName, setJsonFileName] = useState<string>('')
  const [activeSubTab, setActiveSubTab] = useState<'movement' | 'behavioral'>('movement')
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
  const [analysisCompleted, setAnalysisCompleted] = useState(false)
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

  // Rearing Analysis States
  const [rearingROIs, setRearingROIs] = useState<Array<{id: string, name: string, centerX: number, centerY: number, radius: number}>>([])
  const [isDrawingROI, setIsDrawingROI] = useState(false)
  const [currentROIName, setCurrentROIName] = useState<'lower_edge' | 'upper_edge' | 'central_area'>('lower_edge')
  const [selectedKeypointsForRearing, setSelectedKeypointsForRearing] = useState<number[]>([0, 3]) // Default: nose and body center
  const [rearingAnalysisType, setRearingAnalysisType] = useState<'segmentation' | 'pose' | null>(null)
  const [rearingFrameImage, setRearingFrameImage] = useState<HTMLImageElement | null>(null)
  const [showRearingSetup, setShowRearingSetup] = useState(false)
  const [rearingEvents, setRearingEvents] = useState<Array<{start_frame: number, end_frame: number, duration_frames: number}>>([])


  // Lock tab when analyzing
  useEffect(() => {
    onTrackingStateChange?.(isAnalyzing)
  }, [isAnalyzing, onTrackingStateChange])

  // Auto-load first frame when Rearing is checked
  useEffect(() => {
    if (openFieldAnalyses.rearing && videoFile && !rearingFrameImage) {
      loadFirstFrameFromVideo()
    }
  }, [openFieldAnalyses.rearing, videoFile])

  const addLog = (message: string, type: 'info' | 'error' | 'success' = 'info') => {
    const time = new Date().toLocaleTimeString()
    setAnalysisLogs(prev => [...prev, { time, message, type }])
    setTimeout(() => {
      // Scroll only within the logs container, don't affect page scroll
      logsEndRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest', // Don't scroll the page, only the container
        inline: 'nearest'
      })
    }, 100)
  }

  const handleTrackingFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Reset analysis state when new data is loaded
    setAnalysisCompleted(false)
    setAnalysisResult(null)
    setRearingFrameImage(null)
    setShowRearingSetup(false)
    setRearingROIs([])
    setRearingEvents([])

    // Store JSON filename for later use
    setJsonFileName(file.name)

    addLog(`Loading tracking data from ${file.name}...`, 'info')
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target?.result as string)
        setTrackingData(data)
        addLog(`Tracking data loaded successfully: ${data.tracking_data?.length || 0} frames`, 'success')

        // Update video info with correct FPS from JSON if video is already loaded
        if (videoInfo && data.video_info?.fps) {
          const newFrames = Math.round(videoInfo.duration * data.video_info.fps)
          setVideoInfo({
            frames: newFrames,
            duration: videoInfo.duration,
            fps: data.video_info.fps
          })
          addLog(`Updated video frame count with JSON fps: ${newFrames} frames @ ${data.video_info.fps} fps`, 'info')
        }

        // Detect analysis type for rearing
        const firstFrame = data.tracking_data?.[0]
        if (firstFrame?.mask) {
          setRearingAnalysisType('segmentation')
          addLog('Detected segmentation data in JSON', 'info')
        } else if (firstFrame?.keypoints) {
          setRearingAnalysisType('pose')
          addLog('Detected pose data in JSON', 'info')
        }
      } catch (error) {
        console.error('Failed to parse tracking data:', error)
        addLog('Failed to parse tracking data: ' + (error as Error).message, 'error')
      }
    }
    reader.readAsText(file)
  }

  // Load first frame from video for ROI drawing
  const loadFirstFrameFromVideo = async () => {
    if (!videoFile) {
      addLog('Please load a video file first', 'error')
      return
    }

    addLog('Loading first frame from video...', 'info')
    const video = document.createElement('video')
    video.src = URL.createObjectURL(videoFile)

    video.onloadeddata = () => {
      // Seek to first frame
      video.currentTime = 0
    }

    video.onseeked = () => {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')

      if (ctx) {
        ctx.drawImage(video, 0, 0)
        const img = new Image()
        img.onload = () => {
          console.log('First frame image loaded:', img.width, 'x', img.height)
          setRearingFrameImage(img)
          setShowRearingSetup(true)
          // Use setTimeout to ensure state is updated before drawing
          setTimeout(() => {
            drawRearingCanvas()
            addLog('First frame loaded for ROI drawing', 'success')
          }, 100)
        }
        img.onerror = () => {
          addLog('Failed to load frame image', 'error')
        }
        img.src = canvas.toDataURL()
      }

      URL.revokeObjectURL(video.src)
    }

    video.onerror = () => {
      addLog('Failed to load video file', 'error')
      URL.revokeObjectURL(video.src)
    }
  }

  // Draw rearing canvas with frame and ROIs
  const drawRearingCanvas = () => {
    const canvas = canvasRef.current
    if (!canvas || !rearingFrameImage) {
      console.log('drawRearingCanvas - canvas or image missing:', { canvas: !!canvas, image: !!rearingFrameImage })
      return
    }

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      console.log('drawRearingCanvas - no context')
      return
    }

    console.log('Drawing rearing canvas:', rearingFrameImage.width, 'x', rearingFrameImage.height)

    // Set canvas size to match image
    canvas.width = rearingFrameImage.width
    canvas.height = rearingFrameImage.height

    // Draw the frame
    ctx.drawImage(rearingFrameImage, 0, 0)

    // Draw existing ROIs
    rearingROIs.forEach(roi => {
      ctx.strokeStyle = roi.name === 'lower_edge' ? '#ff6b6b' :
                        roi.name === 'upper_edge' ? '#4ecdc4' : '#95e1d3'
      ctx.lineWidth = 3
      ctx.setLineDash([5, 5])
      ctx.beginPath()
      ctx.arc(roi.centerX, roi.centerY, roi.radius, 0, 2 * Math.PI)
      ctx.stroke()
      ctx.setLineDash([])
    })
  }

  // Handle canvas click to draw ROI
  const handleRearingCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawingROI) return

    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const x = (e.clientX - rect.left) * scaleX
    const y = (e.clientY - rect.top) * scaleY

    // For simplicity, using click-drag-release pattern
    // First click sets center, drag sets radius
    const handleMouseMove = (moveEvent: MouseEvent) => {
      const moveX = (moveEvent.clientX - rect.left) * scaleX
      const moveY = (moveEvent.clientY - rect.top) * scaleY
      const radius = Math.sqrt((moveX - x) ** 2 + (moveY - y) ** 2)

      // Redraw with preview
      drawRearingCanvas()
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.strokeStyle = currentROIName === 'lower_edge' ? '#ff6b6b' :
                          currentROIName === 'upper_edge' ? '#4ecdc4' : '#95e1d3'
        ctx.lineWidth = 3
        ctx.setLineDash([5, 5])
        ctx.beginPath()
        ctx.arc(x, y, radius, 0, 2 * Math.PI)
        ctx.stroke()
        ctx.setLineDash([])
      }
    }

    const handleMouseUp = (upEvent: MouseEvent) => {
      const upX = (upEvent.clientX - rect.left) * scaleX
      const upY = (upEvent.clientY - rect.top) * scaleY
      const radius = Math.sqrt((upX - x) ** 2 + (upY - y) ** 2)

      if (radius > 10) { // Minimum radius
        const newROI = {
          id: `${currentROIName}_${Date.now()}`,
          name: currentROIName,
          centerX: x,
          centerY: y,
          radius: radius
        }
        setRearingROIs(prev => [...prev, newROI])
        addLog(`Added ${currentROIName.replace('_', ' ')} ROI`, 'success')
      }

      setIsDrawingROI(false)
      canvas.removeEventListener('mousemove', handleMouseMove)
      canvas.removeEventListener('mouseup', handleMouseUp)
      drawRearingCanvas()
    }

    canvas.addEventListener('mousemove', handleMouseMove)
    canvas.addEventListener('mouseup', handleMouseUp)
  }

  // Clear all rearing ROIs
  const clearRearingROIs = () => {
    setRearingROIs([])
    drawRearingCanvas()
    addLog('Cleared all ROIs', 'info')
  }

  // Effect to redraw canvas when ROIs change
  useEffect(() => {
    if (rearingFrameImage) {
      drawRearingCanvas()
    }
  }, [rearingROIs, rearingFrameImage])

  const handleRunAnalysis = async () => {
    if (!trackingData) {
      addLog('No tracking data loaded', 'error')
      return
    }

    setIsAnalyzing(true)
    setAnalysisResult(null)
    setAnalysisCompleted(false)

    try {
      // Check which analysis to run based on active sub-tab
      if (activeSubTab === 'behavioral') {
        // Behavioral analysis (Rearing, etc.)
        if (openFieldAnalyses.rearing) {
          addLog('Starting Rearing analysis...', 'info')
          addLog('ROIs: ' + JSON.stringify(rearingROIs.map(r => r.name)), 'info')
          addLog(`Processing ${trackingData.tracking_data.length} frames...`, 'info')

          if (!videoFile) {
            addLog('Video file not loaded', 'error')
            return
          }

          // Load video for frame extraction
          const video = document.createElement('video')
          video.src = URL.createObjectURL(videoFile)
          video.muted = true

          // Wait for video to load
          await new Promise<void>((resolve, reject) => {
            video.onloadedmetadata = () => {
              addLog(`Video loaded: ${video.videoWidth}x${video.videoHeight}, duration: ${video.duration.toFixed(2)}s`, 'info')
              resolve()
            }
            video.onerror = () => {
              addLog('Failed to load video file', 'error')
              reject(new Error('Failed to load video'))
            }
          })

          // Process frame by frame
          const frames = trackingData.tracking_data
          const fps = trackingData.video_info.fps || 30
          let rearingCount = 0
          let currentRearingState = false
          let rearingStartFrame = -1
          const detectedEvents: Array<{start_frame: number, end_frame: number, duration_frames: number}> = []

          // Find upper edge ROI (used to detect rearing)
          const upperEdgeROI = rearingROIs.find(r => r.name === 'upper_edge')

          if (!upperEdgeROI) {
            addLog('Upper edge ROI not found - cannot detect rearing', 'error')
            URL.revokeObjectURL(video.src)
            return
          }

          // Find lower edge ROI for additional detection
          const lowerEdgeROI = rearingROIs.find(r => r.name === 'lower_edge')

          // Process each frame with visualization
          for (let i = 0; i < frames.length; i++) {
            const frame = frames[i]

            // Check if rearing occurred in this frame
            let isRearing = false
            let isInLowerEdge = false
            let detectionPoint = { x: 0, y: 0 }

            if (rearingAnalysisType === 'segmentation') {
              // Use centroid for segmentation
              detectionPoint = { x: frame.centroid_x, y: frame.centroid_y }

              // Check if centroid is inside upper edge ROI (rearing)
              const dxUpper = detectionPoint.x - upperEdgeROI.centerX
              const dyUpper = detectionPoint.y - upperEdgeROI.centerY
              const distanceUpper = Math.sqrt(dxUpper * dxUpper + dyUpper * dyUpper)
              isRearing = distanceUpper <= upperEdgeROI.radius

              // Check if centroid is inside lower edge ROI
              if (lowerEdgeROI) {
                const dxLower = detectionPoint.x - lowerEdgeROI.centerX
                const dyLower = detectionPoint.y - lowerEdgeROI.centerY
                const distanceLower = Math.sqrt(dxLower * dxLower + dyLower * dyLower)
                isInLowerEdge = distanceLower <= lowerEdgeROI.radius
              }
            } else if (rearingAnalysisType === 'pose' && frame.keypoints) {
              // Use selected keypoints for pose detection
              for (const kpIndex of selectedKeypointsForRearing) {
                const kp = frame.keypoints[kpIndex]
                if (kp && kp.conf > 0.5) {
                  detectionPoint = { x: kp.x, y: kp.y }

                  // Check upper edge
                  const dxUpper = kp.x - upperEdgeROI.centerX
                  const dyUpper = kp.y - upperEdgeROI.centerY
                  const distanceUpper = Math.sqrt(dxUpper * dxUpper + dyUpper * dyUpper)
                  if (distanceUpper <= upperEdgeROI.radius) {
                    isRearing = true
                  }

                  // Check lower edge
                  if (lowerEdgeROI) {
                    const dxLower = kp.x - lowerEdgeROI.centerX
                    const dyLower = kp.y - lowerEdgeROI.centerY
                    const distanceLower = Math.sqrt(dxLower * dxLower + dyLower * dyLower)
                    if (distanceLower <= lowerEdgeROI.radius) {
                      isInLowerEdge = true
                    }
                  }

                  if (isRearing) break
                }
              }
            }

            // Log rearing events (when state changes)
            if (isRearing && !currentRearingState) {
              rearingCount++
              rearingStartFrame = frame.frame_number
              addLog(`🐭 Rearing detected at frame ${frame.frame_number}!`, 'success')
              currentRearingState = true
            } else if (!isRearing && currentRearingState) {
              const duration = frame.frame_number - rearingStartFrame
              detectedEvents.push({
                start_frame: rearingStartFrame,
                end_frame: frame.frame_number,
                duration_frames: duration
              })
              addLog(`Rearing ended at frame ${frame.frame_number} (duration: ${duration} frames, ${(duration/fps).toFixed(2)}s)`, 'info')
              currentRearingState = false
            }

            // Draw current frame on canvas - optimized for performance
            // Update less frequently for smoother playback (every 10 frames normally)
            // But always update on important events (rearing start/end, leaving lower edge)
            const shouldUpdate = (i % 10 === 0) || isRearing || !isInLowerEdge ||
                                (isRearing !== currentRearingState) // State change

            if (shouldUpdate) {
              // Seek to current frame in video
              const timeInSeconds = frame.frame_number / fps

              // Only seek if necessary (more than 0.2s difference)
              // This reduces unnecessary seeks and improves performance
              const timeDiff = Math.abs(video.currentTime - timeInSeconds)
              if (timeDiff > 0.2) {
                video.currentTime = timeInSeconds

                // Wait for video to seek (with short timeout to prevent hanging)
                await new Promise<void>((resolve) => {
                  const seekTimeout = setTimeout(() => resolve(), 30) // Reduced from 50ms
                  video.onseeked = () => {
                    clearTimeout(seekTimeout)
                    resolve()
                  }
                })
              }

              const canvas = canvasRef.current
              if (canvas) {
                const ctx = canvas.getContext('2d')
                if (ctx && video.readyState >= 2) {
                  // Draw actual video frame
                  canvas.width = video.videoWidth
                  canvas.height = video.videoHeight
                  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

                  // Draw mask if segmentation
                  if (rearingAnalysisType === 'segmentation' && frame.mask && frame.mask.length > 0) {
                    ctx.fillStyle = 'rgba(0, 255, 0, 0.3)' // Green transparent
                    ctx.strokeStyle = '#00ff00'
                    ctx.lineWidth = 2
                    ctx.beginPath()
                    ctx.moveTo(frame.mask[0][0], frame.mask[0][1])
                    for (let j = 1; j < frame.mask.length; j++) {
                      ctx.lineTo(frame.mask[j][0], frame.mask[j][1])
                    }
                    ctx.closePath()
                    ctx.fill()
                    ctx.stroke()
                  }

                  // Draw keypoints if pose
                  if (rearingAnalysisType === 'pose' && frame.keypoints && frame.keypoints.length > 0) {
                    // Define skeleton connections for typical animal pose models
                    const connections = [
                      [0, 1], [0, 2], [1, 3], [2, 4], // Head connections
                      [0, 5], [5, 7], [7, 9],         // Left side
                      [0, 6], [6, 8], [8, 10],        // Right side
                      [5, 6], [5, 11], [6, 12],       // Body
                      [11, 12], [11, 13], [12, 14]    // Rear
                    ]

                    // Draw skeleton lines
                    ctx.strokeStyle = 'rgba(255, 255, 0, 0.7)'
                    ctx.lineWidth = 2
                    connections.forEach(([idx1, idx2]) => {
                      const kp1 = frame.keypoints[idx1]
                      const kp2 = frame.keypoints[idx2]
                      if (kp1 && kp2 && kp1.conf > 0.3 && kp2.conf > 0.3) {
                        ctx.beginPath()
                        ctx.moveTo(kp1.x, kp1.y)
                        ctx.lineTo(kp2.x, kp2.y)
                        ctx.stroke()
                      }
                    })

                    // Draw keypoints
                    frame.keypoints.forEach((kp, idx) => {
                      if (kp && kp.conf > 0.3) {
                        // Color based on confidence
                        const alpha = kp.conf
                        ctx.fillStyle = `rgba(255, 0, 0, ${alpha})`
                        ctx.strokeStyle = '#ffffff'
                        ctx.lineWidth = 1

                        ctx.beginPath()
                        ctx.arc(kp.x, kp.y, 4, 0, 2 * Math.PI)
                        ctx.fill()
                        ctx.stroke()

                        // Draw keypoint index for debugging (optional - can be removed)
                        if (kp.conf > 0.7) {
                          ctx.fillStyle = '#ffffff'
                          ctx.font = '10px monospace'
                          ctx.fillText(idx.toString(), kp.x + 6, kp.y - 6)
                        }
                      }
                    })
                  }

                  // Draw all ROIs
                  rearingROIs.forEach(roi => {
                    // Set color and style based on ROI and detection state
                    if (roi.name === 'upper_edge' && isRearing) {
                      // Upper edge: thick red solid when rearing
                      ctx.strokeStyle = '#ff0000'
                      ctx.lineWidth = 5
                      ctx.setLineDash([]) // Solid line
                    } else if (roi.name === 'lower_edge' && !isInLowerEdge) {
                      // Lower edge: solid line when animal LEFT (warning!)
                      ctx.strokeStyle = '#ff6b6b'
                      ctx.lineWidth = 4
                      ctx.setLineDash([]) // Solid line - animal not on ground!
                    } else {
                      // Default: dashed lines
                      ctx.strokeStyle = roi.name === 'lower_edge' ? '#ff6b6b' :
                                        roi.name === 'upper_edge' ? '#4ecdc4' : '#95e1d3'
                      ctx.lineWidth = 3
                      ctx.setLineDash([5, 5]) // Dashed line
                    }

                    ctx.beginPath()
                    ctx.arc(roi.centerX, roi.centerY, roi.radius, 0, 2 * Math.PI)
                    ctx.stroke()
                    ctx.setLineDash([]) // Reset
                  })

                  // Draw detection point
                  if (detectionPoint.x > 0 && detectionPoint.y > 0) {
                    ctx.fillStyle = isRearing ? '#ff0000' : '#00ff00'
                    ctx.beginPath()
                    ctx.arc(detectionPoint.x, detectionPoint.y, 8, 0, 2 * Math.PI)
                    ctx.fill()
                  }

                  // Draw frame number and state
                  ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
                  ctx.fillRect(10, 10, 220, 30)
                  ctx.fillStyle = isRearing ? '#ff0000' : (isInLowerEdge ? '#00ff00' : '#ffaa00')
                  ctx.font = 'bold 16px monospace'
                  ctx.textAlign = 'left'
                  const stateText = isRearing ? ' [REARING]' : (!isInLowerEdge ? ' [UP]' : '')
                  ctx.fillText(`Frame: ${frame.frame_number}${stateText}`, 20, 30)

                  // Minimal delay for UI responsiveness
                  // Use requestAnimationFrame for smoother updates
                  await new Promise(resolve => {
                    requestAnimationFrame(() => {
                      setTimeout(resolve, 10) // Reduced from 20ms - faster playback
                    })
                  })
                }
              }
            }
          }

          // Cleanup video element
          URL.revokeObjectURL(video.src)

          // Store events for download
          setRearingEvents(detectedEvents)

          // Calculate total duration
          const totalDuration = detectedEvents.reduce((sum, event) => sum + event.duration_frames, 0)
          const totalDurationSec = (totalDuration / fps).toFixed(2)

          addLog(`Rearing analysis completed! Total events: ${rearingCount}, Total duration: ${totalDurationSec}s`, 'success')
          setAnalysisCompleted(true)
        } else {
          addLog('No behavioral analysis selected', 'error')
        }
      } else {
        // Movement analysis (heatmap + velocity)
        addLog('Starting complete analysis (heatmap + movement)...', 'info')
        addLog('Settings: ' + JSON.stringify(heatmapSettings), 'info')

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
            setAnalysisCompleted(true)
          }
          img.src = imageUrl
        }
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
              onChange={async (e) => {
                const file = e.target.files?.[0] || null
                setVideoFile(file)

                if (file) {
                  addLog(`Loading video: ${file.name}...`, 'info')

                  // Extract video information
                  const video = document.createElement('video')
                  video.src = URL.createObjectURL(file)
                  video.preload = 'metadata'

                  video.onloadedmetadata = () => {
                    const duration = video.duration
                    const fps = trackingData?.video_info?.fps || 30 // Use JSON fps if available, otherwise estimate
                    const estimatedFrames = Math.round(duration * fps)

                    setVideoInfo({
                      frames: estimatedFrames,
                      duration: duration,
                      fps: fps
                    })

                    addLog(`Video loaded: ${video.videoWidth}x${video.videoHeight}, ${duration.toFixed(2)}s, ~${estimatedFrames} frames (${fps} fps)`, 'success')
                    URL.revokeObjectURL(video.src)
                  }

                  video.onerror = () => {
                    addLog('Failed to load video metadata', 'error')
                    URL.revokeObjectURL(video.src)
                  }
                }
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-600 file:text-white hover:file:bg-primary-700"
            />
            {videoFile && (
              <div className="mt-2 space-y-1">
                <p className="text-sm text-green-400">✓ {videoFile.name}</p>
                {videoInfo && (
                  <p className="text-xs text-gray-400">
                    • Video: ~{videoInfo.frames} frames ({videoInfo.duration.toFixed(2)}s @ {videoInfo.fps} fps)
                  </p>
                )}
              </div>
            )}
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
            {trackingData && (
              <div className="mt-2 space-y-1">
                <p className="text-sm text-green-400">
                  ✓ {jsonFileName}
                </p>
                <p className="text-xs text-gray-400">
                  • JSON: {trackingData.tracking_data?.length || 0} frames
                </p>
                {rearingAnalysisType && (
                  <p className="text-xs text-gray-400">
                    • {rearingAnalysisType === 'segmentation' ? 'Segmentation' : 'Pose'} detected
                  </p>
                )}
                {videoInfo && videoFile && (
                  <p className={`text-xs font-medium ${
                    Math.abs((trackingData.tracking_data?.length || 0) - videoInfo.frames) <= 2
                      ? 'text-green-400'
                      : 'text-orange-400'
                  }`}>
                    {Math.abs((trackingData.tracking_data?.length || 0) - videoInfo.frames) <= 2
                      ? '✓ Frame count matches video'
                      : `⚠ Frame mismatch: ${Math.abs((trackingData.tracking_data?.length || 0) - videoInfo.frames)} frames difference`
                    }
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Sub-Tabs Navigation */}
        <div className="flex gap-2 mb-6 border-b border-gray-600">
          <button
            onClick={() => setActiveSubTab('movement')}
            className={`px-4 py-3 border-b-2 transition-colors font-medium ${
              activeSubTab === 'movement'
                ? 'border-primary-500 text-primary-400 bg-gray-700/30'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-700/20'
            }`}
          >
            Movement
          </button>
          <button
            onClick={() => setActiveSubTab('behavioral')}
            className={`px-4 py-3 border-b-2 transition-colors font-medium ${
              activeSubTab === 'behavioral'
                ? 'border-primary-500 text-primary-400 bg-gray-700/30'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-700/20'
            }`}
          >
            Behavioral
          </button>
        </div>

        {/* Movement Analysis Tab */}
        {activeSubTab === 'movement' && (
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
        )}

        {/* Behavioral Analysis Tab */}
        {activeSubTab === 'behavioral' && (
        <div className="bg-gray-700/50 rounded-lg p-4 mb-6">
          <div
            className="flex items-center justify-between cursor-pointer hover:bg-gray-600/30 -m-4 p-4 rounded-lg transition-colors"
            onClick={() => setShowBehavioralSettings(!showBehavioralSettings)}
          >
            <div>
              <h3 className="font-semibold text-lg">Behavioral Analysis</h3>
              <p className="text-sm text-gray-400 mt-1">
                Advanced behavioral classification and pattern recognition
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
                      <div className="flex-1">
                        <span className="text-white font-medium">Rearing</span>
                        <p className="text-xs text-gray-400">Requires at least 2-3 ROIs (minimum: lower edge and upper edge, optional: central area) to detect when the animal's body crosses these boundaries</p>
                      </div>
                    </label>

                    {/* Rearing Configuration Panel */}
                    {openFieldAnalyses.rearing && (
                      <div className="ml-7 mt-3 p-4 bg-gray-600/20 rounded-lg border border-gray-600">
                        <h5 className="font-medium text-white mb-3">Rearing Analysis Configuration</h5>

                        {/* Data Type Detection */}
                        {rearingAnalysisType && (
                          <div className="mb-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded">
                            <p className="text-sm text-blue-300">
                              <strong>Detected:</strong> {rearingAnalysisType === 'segmentation' ? 'Segmentation' : 'Pose Detection'} data
                            </p>
                            <p className="text-xs text-blue-200 mt-1">
                              {rearingAnalysisType === 'segmentation'
                                ? 'Using centroid position to detect rearing'
                                : 'Using keypoints to detect rearing'}
                            </p>
                          </div>
                        )}

                        {/* Auto-loaded Frame Status */}
                        {rearingFrameImage && (
                          <div className="mb-3 p-2 bg-green-500/10 border border-green-500/30 rounded text-sm text-green-300">
                            ✓ First frame loaded - Use ROI toolbar above the video in Analysis Preview section below
                          </div>
                        )}

                        {/* ROI Status */}
                        {showRearingSetup && (
                          <div className="space-y-3">
                            {/* ROI List */}
                            {rearingROIs.length > 0 && (
                              <div className="space-y-2">
                                <span className="text-sm font-medium text-gray-300">ROIs Created ({rearingROIs.length})</span>
                                <div className="space-y-1">
                                  {rearingROIs.map(roi => (
                                    <div key={roi.id} className="text-xs text-gray-400 flex items-center justify-between bg-gray-700/50 p-2 rounded">
                                      <span>
                                        <span className={`inline-block w-3 h-3 rounded-full mr-2 ${
                                          roi.name === 'lower_edge' ? 'bg-red-500' :
                                          roi.name === 'upper_edge' ? 'bg-teal-500' : 'bg-green-500'
                                        }`}></span>
                                        {roi.name.replace('_', ' ').toUpperCase()}
                                      </span>
                                      <span className="font-mono">r: {Math.round(roi.radius)}px</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Minimum ROI Warning */}
                            {rearingROIs.length < 2 && (
                              <div className="p-2 bg-orange-500/10 border border-orange-500/30 rounded text-xs text-orange-200">
                                ⚠️ Minimum 2 ROIs required (lower edge + upper edge). Use toolbar above video to draw ROIs.
                              </div>
                            )}

                            {/* Ready Status */}
                            {rearingROIs.length >= 2 && (
                              <div className="p-2 bg-green-500/10 border border-green-500/30 rounded text-xs text-green-200">
                                ✓ Ready for analysis! Click "Run Behavioral Analysis" button below.
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

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
        )}

        {/* Action Buttons */}
        <div className="flex gap-4">
          <button
            onClick={handleRunAnalysis}
            disabled={
              !trackingData ||
              isAnalyzing ||
              // For behavioral tab, check specific requirements
              (activeSubTab === 'behavioral' && (
                // If rearing is selected, need at least 2 ROIs
                (openFieldAnalyses.rearing && rearingROIs.length < 2) ||
                // If no behavioral analysis is selected at all, disable button
                (!openFieldAnalyses.rearing && !openFieldAnalyses.edgeJumps && !openFieldAnalyses.resting && !openFieldAnalyses.grooming &&
                 !elevatedPlusMazeAnalyses.suddenRun && !elevatedPlusMazeAnalyses.panoramicView && !elevatedPlusMazeAnalyses.headDips && !elevatedPlusMazeAnalyses.grooming)
              ))
            }
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <ImageIcon className="w-5 h-5" />
            {isAnalyzing ? 'Running Analysis...' : `Run ${activeSubTab === 'behavioral' ? 'Behavioral' : 'Movement'} Analysis`}
          </button>

          <button
            onClick={async () => {
              if (!trackingData || !analysisCompleted) return

              try {
                if (activeSubTab === 'behavioral' && openFieldAnalyses.rearing) {
                  // Download rearing analysis JSON
                  addLog('Generating rearing analysis JSON...', 'info')

                  // Calculate statistics
                  const fps = trackingData.video_info.fps || 30
                  const totalFrames = rearingEvents.reduce((sum, e) => sum + e.duration_frames, 0)
                  const totalDurationSec = totalFrames / fps
                  const avgDurationFrames = rearingEvents.length > 0 ? totalFrames / rearingEvents.length : 0

                  // Create enhanced JSON with rearing data
                  const rearingData = {
                    ...trackingData,
                    rearing_analysis: {
                      timestamp: new Date().toISOString(),
                      analysis_type: rearingAnalysisType,
                      rois: rearingROIs.map(roi => ({
                        name: roi.name,
                        center_x: roi.centerX,
                        center_y: roi.centerY,
                        radius: roi.radius,
                      })),
                      events: rearingEvents,
                      statistics: {
                        total_events: rearingEvents.length,
                        total_duration_frames: totalFrames,
                        total_duration_seconds: parseFloat(totalDurationSec.toFixed(2)),
                        average_duration_frames: parseFloat(avgDurationFrames.toFixed(2)),
                        average_duration_seconds: parseFloat((avgDurationFrames / fps).toFixed(2)),
                      }
                    }
                  }

                  // Create blob and download
                  const blob = new Blob([JSON.stringify(rearingData, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const link = document.createElement('a')
                  link.href = url

                  // Generate filename: original_json_name_rearing.json
                  const baseName = jsonFileName.replace(/\.json$/i, '') // Remove .json extension if present
                  link.download = `${baseName}_rearing.json`

                  link.click()
                  URL.revokeObjectURL(url)

                  addLog(`Downloaded: ${baseName}_rearing.json`, 'success')
                } else {
                  // Download movement analysis ZIP
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
                }
              } catch (error: any) {
                addLog(`Download failed: ${error.message}`, 'error')
              }
            }}
            disabled={!trackingData || !analysisCompleted}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Download className="w-5 h-5" />
            Download Results
          </button>
        </div>
      </div>

      {/* Results Preview */}
      {(trackingData || rearingFrameImage) && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Analysis Preview</h3>

          {/* ROI Drawing Toolbar */}
          {showRearingSetup && (
            <div className="mb-4 p-3 bg-gray-700/50 rounded-lg border border-gray-600">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-sm font-medium text-gray-300">ROI Tools:</span>

                {/* ROI Selection Buttons */}
                <button
                  onClick={() => {
                    setCurrentROIName('lower_edge')
                    setIsDrawingROI(true)
                  }}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors text-sm ${
                    isDrawingROI && currentROIName === 'lower_edge'
                      ? 'bg-red-600 text-white'
                      : 'bg-gray-600 text-gray-200 hover:bg-gray-500'
                  }`}
                >
                  + Lower Edge
                </button>

                <button
                  onClick={() => {
                    setCurrentROIName('upper_edge')
                    setIsDrawingROI(true)
                  }}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors text-sm ${
                    isDrawingROI && currentROIName === 'upper_edge'
                      ? 'bg-teal-600 text-white'
                      : 'bg-gray-600 text-gray-200 hover:bg-gray-500'
                  }`}
                >
                  + Upper Edge
                </button>

                <button
                  onClick={() => {
                    setCurrentROIName('central_area')
                    setIsDrawingROI(true)
                  }}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors text-sm ${
                    isDrawingROI && currentROIName === 'central_area'
                      ? 'bg-green-600 text-white'
                      : 'bg-gray-600 text-gray-200 hover:bg-gray-500'
                  }`}
                >
                  + Central Area
                </button>

                {/* Separator */}
                <div className="h-8 w-px bg-gray-600"></div>

                {/* Clear ROIs Button */}
                {rearingROIs.length > 0 && (
                  <button
                    onClick={clearRearingROIs}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors text-sm"
                  >
                    Clear ROIs ({rearingROIs.length})
                  </button>
                )}

                {/* Clear All Button */}
                <button
                  onClick={() => {
                    // Clear everything
                    setVideoFile(null)
                    setTrackingData(null)
                    setRearingFrameImage(null)
                    setShowRearingSetup(false)
                    setRearingROIs([])
                    setAnalysisCompleted(false)
                    setAnalysisResult(null)
                    addLog('All data cleared', 'info')
                  }}
                  className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors text-sm ml-auto"
                >
                  Clear All
                </button>

                {/* Drawing Instructions */}
                {isDrawingROI && (
                  <div className="w-full mt-2 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded text-xs text-yellow-200">
                    Click and drag on the video below to draw a circular ROI
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Video Canvas */}
          <div className="bg-black rounded-lg overflow-hidden border border-gray-700 flex items-center justify-center" style={{ minHeight: '400px' }}>
            <canvas
              ref={canvasRef}
              onClick={showRearingSetup ? handleRearingCanvasClick : undefined}
              className={showRearingSetup && isDrawingROI ? 'cursor-crosshair' : ''}
              style={{ maxWidth: '100%', maxHeight: '600px', height: 'auto', width: 'auto' }}
            />
          </div>

          {/* Statistics - Only show when trackingData is loaded */}
          {trackingData && (
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
          )}
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
