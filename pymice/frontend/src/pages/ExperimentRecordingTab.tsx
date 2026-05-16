import { useEffect, useRef, useState } from 'react'
import { Camera, Square, Circle, Play, StopCircle, Download, FolderOpen } from 'lucide-react'
import { cameraApi, experimentApi, trackingApi } from '@/services/api'
import ROICanvas from '@/components/ROICanvas'
import type { ROI, ROIPreset, ExperimentEvent } from '@/types'
import IntegrationsPanel from '@/components/IntegrationsPanel'
import TriggersPanel from '@/components/TriggersPanel'
import EventLogPanel from '@/components/EventLogPanel'
import FolderPickerModal from '@/components/FolderPickerModal'

interface Props {
  onTrackingStateChange?: (isActive: boolean) => void
}

type View = 'setup' | 'live' | 'done'

export default function ExperimentRecordingTab({ onTrackingStateChange }: Props = {}) {
  const [view, setView] = useState<View>('setup')
  const [devices, setDevices] = useState<number[]>([])
  const [selectedDevice, setSelectedDevice] = useState<number>(0)
  const [resolution, setResolution] = useState({ width: 640, height: 480 })
  const [brightness, setBrightness] = useState<number>(50)
  const [isStreaming, setIsStreaming] = useState(false)
  const [rois, setRois] = useState<ROI[]>([])
  const [tool, setTool] = useState<'Rectangle' | 'Circle' | 'Polygon'>('Rectangle')

  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [outputDir, setOutputDir] = useState<string>('temp/experiments')
  const [showFolderPicker, setShowFolderPicker] = useState(false)

  const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null)
  const pollRef = useRef<number | null>(null)

  const [expId, setExpId] = useState<string | null>(null)
  const [activeRoi, setActiveRoi] = useState<number | null>(null)
  const [events, setEvents] = useState<ExperimentEvent[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const [artifacts, setArtifacts] = useState<Record<string, string> | null>(null)

  useEffect(() => {
    onTrackingStateChange?.(view === 'live')
  }, [view, onTrackingStateChange])

  useEffect(() => {
    cameraApi.listDevices().then((r) => {
      const data = r.data.data as unknown
      const list: number[] = Array.isArray(data)
        ? (data as number[])
        : (data as { devices?: number[] })?.devices ?? []
      setDevices(list)
      if (list.length > 0) setSelectedDevice(list[0])
    })
    trackingApi.listModels().then((r) => {
      const data = r.data.data as unknown
      const list: string[] = Array.isArray(data)
        ? (data as string[])
        : (data as { models?: string[] })?.models ?? []
      setModels(list)
      if (list.length > 0) setSelectedModel(list[0])
    })
  }, [])

  const pollFrame = async () => {
    try {
      const r = await cameraApi.getFrame()
      const url = URL.createObjectURL(r.data)
      const img = new Image()
      img.onload = () => {
        setBgImage(img)
        URL.revokeObjectURL(url)
      }
      img.src = url
    } catch {
      /* ignore transient errors */
    }
  }

  const startStream = async () => {
    const r = await cameraApi.startStream(selectedDevice, {
      width: resolution.width,
      height: resolution.height,
      brightness,
    })
    // Adopt the resolution the camera actually delivered (some hardware rounds).
    if (r.data.data?.width && r.data.data?.height) {
      setResolution({ width: r.data.data.width, height: r.data.data.height })
    }
    setIsStreaming(true)
    pollRef.current = window.setInterval(pollFrame, 33)
  }

  const stopStream = async () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    await cameraApi.stopStream()
    setIsStreaming(false)
    setBgImage(null)
  }

  // Push brightness changes live while streaming
  useEffect(() => {
    if (!isStreaming) return
    const id = window.setTimeout(() => {
      cameraApi.setProperties({ brightness }).catch(() => { /* camera may not support */ })
    }, 150)
    return () => window.clearTimeout(id)
  }, [brightness, isStreaming])

  const startExperiment = async () => {
    const preset: ROIPreset = {
      preset_name: 'live',
      description: 'Created in Experiment Recording',
      timestamp: new Date().toISOString(),
      frame_width: resolution.width,
      frame_height: resolution.height,
      rois,
    }
    const r = await experimentApi.start({
      device_id: selectedDevice,
      model_name: selectedModel,
      rois: preset,
      confidence_threshold: 0.5,
      iou_threshold: 0.5,
      inference_size: 640,
      triggers: [],
      output_base_dir: outputDir.trim() || 'temp/experiments',
    })
    if (!r.data.success || !r.data.data) {
      alert(`Failed to start experiment: ${r.data.error}`)
      return
    }
    setExpId(r.data.data.exp_id)
    setView('live')
    setEvents([])

    wsRef.current = experimentApi.subscribeEvents(
      (evt) => {
        setEvents((prev) => [...prev.slice(-200), evt])
        if (evt.type === 'roi_entry') setActiveRoi(evt.roi_index as number)
        if (evt.type === 'roi_exit') setActiveRoi(null)
        if (evt.type === 'tick' && typeof evt.active_roi !== 'undefined') {
          setActiveRoi((evt.active_roi as number | null) ?? null)
        }
        if (evt.type === 'stopped') {
          setView('done')
        }
      },
      () => { /* ws closed */ },
    )
  }

  const stopExperiment = async () => {
    const r = await experimentApi.stop()
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (r.data.success && r.data.data) {
      setArtifacts(r.data.data.artifacts)
    }
    setView('done')
  }

  const reset = () => {
    setExpId(null)
    setArtifacts(null)
    setEvents([])
    setActiveRoi(null)
    setView('setup')
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Camera className="w-5 h-5 text-primary-500" />
          Experiment Recording
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium mb-1">Camera Device</label>
            <select
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(Number(e.target.value))}
              disabled={isStreaming || view === 'live'}
              className="w-full bg-white dark:bg-gray-700 border rounded px-3 py-2"
            >
              {devices.map((d) => (
                <option key={d} value={d}>Camera {d}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Resolution</label>
            <select
              value={`${resolution.width}x${resolution.height}`}
              onChange={(e) => {
                const [w, h] = e.target.value.split('x').map(Number)
                setResolution({ width: w, height: h })
              }}
              disabled={isStreaming || view === 'live'}
              className="w-full bg-white dark:bg-gray-700 border rounded px-3 py-2"
            >
              <option value="640x480">640 × 480</option>
              <option value="1280x720">1280 × 720 (HD)</option>
              <option value="1920x1080">1920 × 1080 (Full HD)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">YOLO Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={view === 'live'}
              className="w-full bg-white dark:bg-gray-700 border rounded px-3 py-2"
            >
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={isStreaming ? stopStream : startStream}
              disabled={view === 'live'}
              className={`w-full px-4 py-2 rounded text-white ${
                isStreaming ? 'bg-red-600' : 'bg-primary-600'
              } disabled:opacity-50`}
            >
              {isStreaming ? (<><Square className="inline w-4 h-4 mr-2" /> Stop Preview</>) :
                            (<><Circle className="inline w-4 h-4 mr-2" /> Start Preview</>)}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium mb-1">
              Brightness <span className="text-gray-500">({brightness})</span>
            </label>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={brightness}
              onChange={(e) => setBrightness(Number(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Output Folder</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
                disabled={view === 'live'}
                placeholder="temp/experiments"
                className="flex-1 bg-white dark:bg-gray-700 border rounded px-3 py-2 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => setShowFolderPicker(true)}
                disabled={view === 'live'}
                className="px-3 py-2 border rounded inline-flex items-center gap-1 text-sm disabled:opacity-50 bg-white dark:bg-gray-700"
              >
                <FolderOpen className="w-4 h-4" /> Browse...
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Backend creates <code>&lt;folder&gt;/&lt;exp_id&gt;/</code> with raw.mp4, tracking.jsonl, events.jsonl, metadata.json
            </p>
          </div>
        </div>

        {view === 'setup' && isStreaming && (
          <div className="flex gap-2 mb-3">
            {(['Rectangle', 'Circle', 'Polygon'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTool(t)}
                className={`px-3 py-1 rounded text-sm border ${
                  tool === t ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-700'
                }`}
              >
                {t}
              </button>
            ))}
            <button
              onClick={() => setRois([])}
              disabled={rois.length === 0}
              className="px-3 py-1 rounded text-sm border bg-white dark:bg-gray-700 disabled:opacity-40"
            >
              Clear ROIs
            </button>
          </div>
        )}

        <ROICanvas
          width={resolution.width}
          height={resolution.height}
          rois={rois}
          onRoisChange={setRois}
          mode={view === 'live' ? 'live-overlay' : view === 'done' ? 'view-only' : 'edit'}
          activeRoiIndex={activeRoi}
          backgroundFrame={bgImage}
          tool={tool}
        />

        <div className="mt-4 flex gap-3">
          {view === 'setup' && (
            <button
              onClick={startExperiment}
              disabled={!isStreaming || rois.length === 0 || !selectedModel}
              className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-2 rounded flex items-center gap-2"
            >
              <Play className="w-4 h-4" /> Start Recording
            </button>
          )}
          {view === 'live' && (
            <button
              onClick={stopExperiment}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded flex items-center gap-2"
            >
              <StopCircle className="w-4 h-4" /> Stop Recording
            </button>
          )}
          {view === 'done' && (
            <button onClick={reset} className="bg-primary-600 text-white px-4 py-2 rounded">
              New Recording
            </button>
          )}
        </div>

        {view === 'done' && artifacts && expId && (
          <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded">
            <h3 className="font-medium mb-2">Artifacts</h3>
            <ul className="space-y-1 text-sm">
              {(['raw.mp4', 'tracking.jsonl', 'events.jsonl', 'metadata.json'] as const).map((a) => (
                <li key={a}>
                  <a
                    href={experimentApi.artifactUrl(expId, a)}
                    download
                    className="text-primary-600 hover:underline inline-flex items-center gap-1"
                  >
                    <Download className="w-3 h-3" /> {a}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {view === 'setup' && (
        <>
          <IntegrationsPanel />
          <TriggersPanel disabled />
        </>
      )}
      {view === 'live' && expId && (
        <>
          <TriggersPanel expId={expId} />
          <EventLogPanel events={events} />
        </>
      )}

      {showFolderPicker && (
        <FolderPickerModal
          initialPath={outputDir}
          onSelect={(path) => {
            setOutputDir(path)
            setShowFolderPicker(false)
          }}
          onClose={() => setShowFolderPicker(false)}
        />
      )}
    </div>
  )
}
