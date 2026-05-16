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

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

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
  const [segmentMaxMb, setSegmentMaxMb] = useState<number>(1024)
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [liveSegmentIndex, setLiveSegmentIndex] = useState<number | null>(null)
  const [doneFiles, setDoneFiles] = useState<import('@/types').ArtifactFile[]>([])

  const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null)
  const pollRef = useRef<number | null>(null)
  const pollAliveRef = useRef<boolean>(false)
  const pollInflightRef = useRef<boolean>(false)
  const [streamBusy, setStreamBusy] = useState<boolean>(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [recordingBusy, setRecordingBusy] = useState<boolean>(false)
  const [recordingError, setRecordingError] = useState<string | null>(null)

  const [expId, setExpId] = useState<string | null>(null)
  const [activeRoi, setActiveRoi] = useState<number | null>(null)
  const [events, setEvents] = useState<ExperimentEvent[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const [liveFps, setLiveFps] = useState<number | null>(null)
  const [liveFrames, setLiveFrames] = useState<number | null>(null)
  const [liveDevice, setLiveDevice] = useState<string | null>(null)

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

  // Self-pacing poll: next fetch is scheduled only after the previous one
  // resolves, so slow responses don't pile up requests. Pace target is ~33ms
  // (≈30 FPS) but the server's actual rate dominates.
  const pollFrame = async () => {
    if (!pollAliveRef.current) return
    if (pollInflightRef.current) {
      pollRef.current = window.setTimeout(pollFrame, 16)
      return
    }
    pollInflightRef.current = true
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
    } finally {
      pollInflightRef.current = false
      if (pollAliveRef.current) {
        pollRef.current = window.setTimeout(pollFrame, 16)
      }
    }
  }

  const startStream = async () => {
    if (streamBusy) return
    setStreamBusy(true)
    setStreamError(null)
    try {
      const r = await cameraApi.startStream(selectedDevice, {
        width: resolution.width,
        height: resolution.height,
        brightness,
      })
      if (r.data.data?.width && r.data.data?.height) {
        setResolution({ width: r.data.data.width, height: r.data.data.height })
      }
      setIsStreaming(true)
      pollAliveRef.current = true
      pollFrame()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setStreamError(typeof detail === 'string' ? detail : String(e))
    } finally {
      setStreamBusy(false)
    }
  }

  const stopStream = async () => {
    if (streamBusy) return
    // Optimistic UI update — kill the poll immediately so frames stop being fetched,
    // even if the backend call itself is slow.
    pollAliveRef.current = false
    if (pollRef.current) {
      clearTimeout(pollRef.current)
      pollRef.current = null
    }
    setIsStreaming(false)
    setBgImage(null)
    setStreamBusy(true)
    setStreamError(null)
    try {
      await cameraApi.stopStream()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setStreamError(typeof detail === 'string' ? detail : String(e))
    } finally {
      setStreamBusy(false)
    }
  }

  // Tab/window close → fire a stateless beacon to release the camera. This is
  // the only reliable cleanup path when the user just closes the tab.
  useEffect(() => {
    const onUnload = () => {
      try {
        navigator.sendBeacon('/api/camera/stream/stop')
      } catch {
        /* ignore */
      }
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [])

  // Push brightness changes live while streaming
  useEffect(() => {
    if (!isStreaming) return
    const id = window.setTimeout(() => {
      cameraApi.setProperties({ brightness }).catch(() => { /* camera may not support */ })
    }, 150)
    return () => window.clearTimeout(id)
  }, [brightness, isStreaming])

  const startExperiment = async () => {
    if (recordingBusy) return
    setRecordingError(null)
    setRecordingBusy(true)
    const preset: ROIPreset = {
      preset_name: 'live',
      description: 'Created in Experiment Recording',
      timestamp: new Date().toISOString(),
      frame_width: resolution.width,
      frame_height: resolution.height,
      rois,
    }
    let r
    try {
      r = await experimentApi.start({
        device_id: selectedDevice,
        model_name: selectedModel,
        rois: preset,
        confidence_threshold: 0.5,
        iou_threshold: 0.5,
        inference_size: 640,
        triggers: [],
        output_base_dir: outputDir.trim() || 'temp/experiments',
        segment_max_mb: segmentMaxMb,
      })
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setRecordingError(typeof detail === 'string' ? detail : JSON.stringify(detail ?? e))
      setRecordingBusy(false)
      return
    }
    if (!r.data.success || !r.data.data) {
      setRecordingError(r.data.error ?? 'Backend returned success=false')
      setRecordingBusy(false)
      return
    }
    setExpId(r.data.data.exp_id)
    setView('live')
    setEvents([])
    setRecordingBusy(false)

    wsRef.current = experimentApi.subscribeEvents(
      (evt) => {
        setEvents((prev) => [...prev.slice(-200), evt])
        if (evt.type === 'roi_entry') setActiveRoi(evt.roi_index as number)
        if (evt.type === 'roi_exit') setActiveRoi(null)
        if (evt.type === 'tick') {
          if (typeof evt.active_roi !== 'undefined') {
            setActiveRoi((evt.active_roi as number | null) ?? null)
          }
          if (typeof evt.fps_actual === 'number') setLiveFps(evt.fps_actual)
          if (typeof evt.frame_idx === 'number') setLiveFrames(evt.frame_idx)
        }
        if (evt.type === 'segment_rotated' && typeof evt.new_index === 'number') {
          setLiveSegmentIndex(evt.new_index)
        }
        if (evt.type === 'device_fallback') {
          setLiveDevice(String(evt.to ?? 'cpu'))
        }
        if (evt.type === 'stopped') {
          setView('done')
        }
      },
      () => { /* ws closed */ },
    )
  }

  const stopExperiment = async () => {
    await experimentApi.stop()
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setView('done')
  }

  // When we transition into done, fetch the actual files list (segments + events + metadata).
  useEffect(() => {
    if (view !== 'done' || !expId) return
    experimentApi.listArtifacts(expId)
      .then((r) => setDoneFiles(r.data.data?.files ?? []))
      .catch(() => setDoneFiles([]))
  }, [view, expId])

  const reset = () => {
    setExpId(null)
    setEvents([])
    setActiveRoi(null)
    setLiveFps(null)
    setLiveFrames(null)
    setLiveSegmentIndex(null)
    setLiveDevice(null)
    setDoneFiles([])
    setView('setup')
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Camera className="w-5 h-5 text-primary-500" />
          Experiment Recording
        </h2>

        {/* Camera section: device + resolution + preview toggle live together.
            Preview is a small toggle on the right (camera management), distinct
            from Start Recording (the primary action below the canvas). */}
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
          <div>
            <label className="block text-sm font-medium mb-1">Preview</label>
            <button
              onClick={isStreaming ? stopStream : startStream}
              disabled={view === 'live' || streamBusy}
              className={`w-full px-3 py-2 rounded text-white text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed ${
                isStreaming
                  ? 'bg-gray-600 hover:bg-gray-700'
                  : 'bg-primary-600 hover:bg-primary-700'
              }`}
              title={isStreaming ? 'Turn the camera off' : 'Turn the camera on (no recording)'}
            >
              {streamBusy
                ? '…'
                : isStreaming
                  ? <><Square className="w-4 h-4" /> Stop Preview</>
                  : <><Circle className="w-4 h-4" /> Start Preview</>}
            </button>
            {streamError && (
              <p className="text-xs text-red-600 dark:text-red-400 mt-1 truncate" title={streamError}>
                {streamError}
              </p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
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
              disabled={!isStreaming || view === 'live'}
              className="w-full disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">
              Segment size <span className="text-gray-500">(MB)</span>
            </label>
            <input
              type="number"
              min={10}
              max={10240}
              step={64}
              value={segmentMaxMb}
              onChange={(e) => setSegmentMaxMb(Number(e.target.value))}
              disabled={view === 'live'}
              className="w-full bg-white dark:bg-gray-700 border rounded px-3 py-2"
            />
            <p className="text-xs text-gray-500 mt-1">
              Splits raw.mp4 into raw_NNN.mp4 every {segmentMaxMb} MB or 30 min — whichever comes first.
            </p>
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

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: tool bar, canvas, recording controls, artifacts */}
          <div className="lg:col-span-2 space-y-3">
            {/* Tool bar — always visible, disabled when no preview or while recording */}
            <div className="flex gap-2">
              {(['Rectangle', 'Circle', 'Polygon'] as const).map((t) => {
                const toolsEnabled = view === 'setup' && isStreaming
                return (
                  <button
                    key={t}
                    onClick={() => setTool(t)}
                    disabled={!toolsEnabled}
                    className={`px-3 py-1 rounded text-sm border ${
                      tool === t && toolsEnabled
                        ? 'bg-primary-600 text-white'
                        : 'bg-white dark:bg-gray-700'
                    } disabled:opacity-40`}
                  >
                    {t}
                  </button>
                )
              })}
              <button
                onClick={() => setRois([])}
                disabled={view !== 'setup' || !isStreaming || rois.length === 0}
                className="px-3 py-1 rounded text-sm border bg-white dark:bg-gray-700 disabled:opacity-40"
              >
                Clear ROIs
              </button>
            </div>

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

            {/* Recording action — the only primary action below the canvas.
                Preview lives in the top row (camera management). This row is
                a single big button whose label/color reflects the current
                view: Start Recording (setup) → Stop Recording (live) → New
                Recording (done). Hints and errors hang below the button. */}
            <div className="flex flex-col gap-2">
              {view === 'setup' && (() => {
                const blockers: string[] = []
                if (!isStreaming) blockers.push('Start Preview first')
                if (!selectedModel) blockers.push('Select a YOLO model')
                const isDisabled = blockers.length > 0 || recordingBusy
                return (
                  <>
                    <button
                      onClick={startExperiment}
                      disabled={isDisabled}
                      title={blockers.length ? blockers.join(' · ') : 'Begin recording video + tracking data'}
                      className="bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-3 rounded font-medium flex items-center justify-center gap-2 self-start"
                    >
                      <Play className="w-5 h-5" />
                      {recordingBusy ? 'Starting…' : 'Start Recording'}
                    </button>
                    {blockers.length > 0 && (
                      <span className="text-xs text-amber-600 dark:text-amber-400">
                        {blockers.join(' · ')}
                      </span>
                    )}
                    {!blockers.length && rois.length === 0 && (
                      <span className="text-xs text-gray-500">
                        No ROIs — video + tracking will record (no roi_entry/exit events).
                      </span>
                    )}
                    {recordingError && (
                      <span className="text-xs text-red-600 dark:text-red-400">
                        Recording failed: {recordingError}
                      </span>
                    )}
                  </>
                )
              })()}
              {view === 'live' && (
                <>
                  <button
                    onClick={stopExperiment}
                    className="bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded font-medium flex items-center justify-center gap-2 self-start"
                  >
                    <StopCircle className="w-5 h-5" />
                    Stop Recording
                  </button>
                  <span className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1">
                    <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    Recording in progress — camera settings are locked.
                  </span>
                </>
              )}
              {view === 'done' && (
                <button
                  onClick={reset}
                  className="bg-primary-600 hover:bg-primary-700 text-white px-6 py-3 rounded font-medium flex items-center justify-center gap-2 self-start"
                >
                  <Play className="w-5 h-5" />
                  New Recording
                </button>
              )}
            </div>

            {view === 'done' && expId && (
              <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded">
                <h3 className="font-medium mb-2">
                  Artifacts <span className="text-xs text-gray-500">({doneFiles.length} files)</span>
                </h3>
                {doneFiles.length === 0 ? (
                  <p className="text-sm text-gray-500">Loading…</p>
                ) : (
                  <ul className="space-y-1 text-sm max-h-64 overflow-auto">
                    {doneFiles.map((f) => (
                      <li key={f.name} className="flex items-center gap-2">
                        <a
                          href={experimentApi.artifactUrl(expId, f.name)}
                          download
                          className="text-primary-600 hover:underline inline-flex items-center gap-1 flex-1 min-w-0"
                        >
                          <Download className="w-3 h-3 flex-shrink-0" />
                          <span className="truncate">{f.name}</span>
                        </a>
                        <span className="text-xs text-gray-500 flex-shrink-0">
                          {f.kind} · {formatBytes(f.size)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Right column: status + integrations + triggers + event log */}
          <div className="lg:col-span-1 space-y-3 flex flex-col">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700 text-sm space-y-1">
              <div className="font-semibold flex items-center gap-2">Status</div>
              {view === 'setup' && (
                <>
                  <div className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${isStreaming ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
                    <span>{isStreaming ? 'Preview running' : 'Idle'}</span>
                  </div>
                  <div className="text-gray-500">Resolution: {resolution.width}×{resolution.height}</div>
                  <div className="text-gray-500">ROIs drawn: {rois.length}</div>
                  <div className="text-gray-500">Output: <code className="text-xs">{outputDir}</code></div>
                </>
              )}
              {view === 'live' && (
                <>
                  <div className="flex items-center gap-2">
                    <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    <span>Recording</span>
                  </div>
                  <div className="text-gray-500">exp_id: <code className="text-xs">{expId}</code></div>
                  <div className="text-gray-500">FPS: {liveFps != null ? liveFps.toFixed(1) : '—'}</div>
                  <div className="text-gray-500">Frames: {liveFrames ?? 0}</div>
                  <div className="text-gray-500">Segment: #{liveSegmentIndex ?? 0}</div>
                  <div className="text-gray-500">Active ROI: {activeRoi ?? '—'}</div>
                  {liveDevice && (
                    <div className="text-amber-600 dark:text-amber-400 text-xs">
                      ⚠ Running on {liveDevice.toUpperCase()} (GPU incompatible)
                    </div>
                  )}
                </>
              )}
              {view === 'done' && (
                <>
                  <div className="flex items-center gap-2">
                    <span className="inline-block w-2 h-2 rounded-full bg-blue-500" />
                    <span>Stopped</span>
                  </div>
                  <div className="text-gray-500">exp_id: <code className="text-xs">{expId}</code></div>
                  <div className="text-gray-500">Frames: {liveFrames ?? 0}</div>
                </>
              )}
            </div>
            <IntegrationsPanel />
            {view === 'live' && expId
              ? <TriggersPanel expId={expId} />
              : <TriggersPanel disabled />}
            {view === 'live' && <EventLogPanel events={events} />}
          </div>
        </div>
      </div>

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
