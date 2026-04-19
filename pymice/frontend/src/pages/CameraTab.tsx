import { useState, useRef, useEffect } from 'react'
import { Camera, Video, Download, Square, Circle } from 'lucide-react'
import { cameraApi } from '@/services/api'

interface CameraTabProps {
  onTrackingStateChange?: (isTracking: boolean) => void
}

export default function CameraTab({ onTrackingStateChange }: CameraTabProps = {}) {
  const [devices, setDevices] = useState<number[]>([])
  const [selectedDevice, setSelectedDevice] = useState<number>(0)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [recordingFilename, setRecordingFilename] = useState('')
  const [resolution, setResolution] = useState({ width: 640, height: 480 })
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const intervalRef = useRef<number | null>(null)

  useEffect(() => {
    loadDevices()
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])

  // Lock tab when recording
  useEffect(() => {
    onTrackingStateChange?.(isRecording)
  }, [isRecording, onTrackingStateChange])

  const loadDevices = async () => {
    try {
      const response = await cameraApi.listDevices()
      if (response.data.success && response.data.data) {
        // A API retorna {success: true, data: {devices: [...]}}
        const deviceList = Array.isArray(response.data.data)
          ? response.data.data
          : response.data.data.devices || []

        setDevices(deviceList)
        if (deviceList.length > 0) {
          setSelectedDevice(deviceList[0])
        }
      }
    } catch (error) {
      console.error('Failed to load devices:', error)
      setDevices([]) // Garantir que seja array mesmo em erro
    }
  }

  const startStream = async () => {
    try {
      await cameraApi.startStream(selectedDevice)
      setIsStreaming(true)

      // Calculate display size maintaining aspect ratio
      const maxDisplayWidth = 1200 // Max width in pixels
      const maxDisplayHeight = 600 // Max height in pixels
      const aspectRatio = resolution.width / resolution.height

      let displayWidth = maxDisplayWidth
      let displayHeight = maxDisplayWidth / aspectRatio

      if (displayHeight > maxDisplayHeight) {
        displayHeight = maxDisplayHeight
        displayWidth = maxDisplayHeight * aspectRatio
      }

      // Set canvas display size via CSS
      const canvas = canvasRef.current
      if (canvas) {
        canvas.style.width = `${displayWidth}px`
        canvas.style.height = `${displayHeight}px`
      }

      // Start polling for frames
      intervalRef.current = window.setInterval(async () => {
        try {
          const response = await cameraApi.getFrame()
          const canvas = canvasRef.current
          if (canvas) {
            const ctx = canvas.getContext('2d')
            if (ctx) {
              const img = new Image()
              img.onload = () => {
                // Set internal canvas dimensions to actual resolution
                canvas.width = resolution.width
                canvas.height = resolution.height
                ctx.drawImage(img, 0, 0, resolution.width, resolution.height)
              }
              img.src = URL.createObjectURL(response.data)
            }
          }
        } catch (error) {
          console.error('Failed to get frame:', error)
        }
      }, 33) // ~30 FPS
    } catch (error) {
      console.error('Failed to start stream:', error)
    }
  }

  const stopStream = async () => {
    try {
      await cameraApi.stopStream()
      setIsStreaming(false)

      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    } catch (error) {
      console.error('Failed to stop stream:', error)
    }
  }

  const startRecording = async () => {
    try {
      const response = await cameraApi.startRecording(selectedDevice)
      if (response.data.success && response.data.data) {
        setIsRecording(true)
        // A API retorna {filename: "..."}
        const filename = typeof response.data.data === 'string'
          ? response.data.data
          : response.data.data.filename
        setRecordingFilename(filename)
      }
    } catch (error) {
      console.error('Failed to start recording:', error)
      alert('Erro ao iniciar gravação: ' + error.message)
    }
  }

  const stopRecording = async () => {
    try {
      await cameraApi.stopRecording()
      setIsRecording(false)
    } catch (error) {
      console.error('Failed to stop recording:', error)
    }
  }

  const downloadRecording = async () => {
    if (!recordingFilename) return

    try {
      const response = await cameraApi.downloadVideo(recordingFilename)

      // Criar blob e fazer download
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', recordingFilename)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to download recording:', error)
      alert('Erro ao baixar gravação: ' + error.message)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Camera className="w-5 h-5 text-primary-500" />
          Video Experiment & Camera Control
        </h2>

        {/* Camera Settings */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Camera Device
            </label>
            <select
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(Number(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={isStreaming}
            >
              {devices.map((device) => (
                <option key={device} value={device}>
                  Camera {device}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Resolution
            </label>
            <select
              value={`${resolution.width}x${resolution.height}`}
              onChange={(e) => {
                const [width, height] = e.target.value.split('x').map(Number)
                setResolution({ width, height })
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={isStreaming}
            >
              <option value="640x480">640x480</option>
              <option value="1280x720">1280x720 (HD)</option>
              <option value="1920x1080">1920x1080 (Full HD)</option>
            </select>
          </div>

          <div className="flex items-end gap-2">
            <button
              onClick={isStreaming ? stopStream : startStream}
              className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 ${
                isStreaming
                  ? 'bg-red-600 hover:bg-red-700 text-white'
                  : 'bg-primary-600 hover:bg-primary-700 text-white'
              }`}
            >
              {isStreaming ? (
                <>
                  <Square className="w-4 h-4" />
                  Stop Stream
                </>
              ) : (
                <>
                  <Circle className="w-4 h-4" />
                  Start Stream
                </>
              )}
            </button>
          </div>
        </div>

        {/* Video Canvas */}
        <div className="mb-6 bg-black rounded-lg overflow-hidden border border-gray-700 flex items-center justify-center" style={{ minHeight: '400px' }}>
          <canvas
            ref={canvasRef}
            className="max-w-full"
          />
        </div>

        {/* Recording Controls */}
        <div className="flex gap-4">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={!isStreaming}
            className={`px-6 py-3 rounded-lg font-medium transition-colors flex items-center gap-2 ${
              !isStreaming
                ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                : isRecording
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {isRecording ? (
              <>
                <Square className="w-5 h-5" />
                Stop Recording
              </>
            ) : (
              <>
                <Video className="w-5 h-5" />
                Start Recording
              </>
            )}
          </button>

          {isRecording && (
            <div className="flex items-center gap-2 px-4 py-3 bg-red-900/20 border border-red-600 rounded-lg">
              <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
              <span className="text-red-400 font-medium">Recording: {recordingFilename}</span>
            </div>
          )}

          {recordingFilename && !isRecording && (
            <button
              onClick={downloadRecording}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
            >
              <Download className="w-5 h-5" />
              Download Last Recording
            </button>
          )}
        </div>
      </div>

      {/* Info Panel */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-3">Camera Information</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-gray-400">Status</div>
            <div className="font-medium text-white">
              {isStreaming ? (
                <span className="text-green-400">Streaming</span>
              ) : (
                <span className="text-gray-400">Stopped</span>
              )}
            </div>
          </div>
          <div>
            <div className="text-gray-400">Resolution</div>
            <div className="font-medium text-white">
              {resolution.width}x{resolution.height}
            </div>
          </div>
          <div>
            <div className="text-gray-400">Device</div>
            <div className="font-medium text-white">Camera {selectedDevice}</div>
          </div>
          <div>
            <div className="text-gray-400">FPS</div>
            <div className="font-medium text-white">~30</div>
          </div>
        </div>
      </div>
    </div>
  )
}
