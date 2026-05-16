import axios from 'axios'
import type {
  ApiResponse,
  UploadResponse,
  VideoInfo,
  TrackingData,
  ROIPreset,
  ProcessingProgress,
  HeatmapSettings,
  Integration,
  TriggerRule,
  ExperimentStartRequest,
  ExperimentStatus,
  SerialPort,
  ExperimentEvent,
} from '@/types'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 minutes for long processing tasks
})

// Camera API
export const cameraApi = {
  listDevices: () => api.get<ApiResponse<number[]>>('/camera/devices'),

  startStream: (
    deviceId: number,
    opts?: { width?: number; height?: number; brightness?: number },
  ) =>
    api.post<ApiResponse<{ message: string; width: number; height: number }>>(
      '/camera/stream/start',
      { device_id: deviceId, ...opts },
    ),

  stopStream: () =>
    api.post<ApiResponse<void>>('/camera/stream/stop'),

  setProperties: (props: { brightness?: number }) =>
    api.post<ApiResponse<{ applied: Record<string, number> }>>('/camera/properties', props),

  getFrame: () =>
    api.get<Blob>('/camera/frame', { responseType: 'blob' }),

  startRecording: (deviceId: number, filename?: string) =>
    api.post<ApiResponse<string>>('/camera/record/start', {
      device_id: deviceId,
      filename
    }),

  stopRecording: () =>
    api.post<ApiResponse<string>>('/camera/record/stop'),

  downloadVideo: (filename: string) =>
    api.get(`/video/download/${filename}`, { responseType: 'blob' }),
}

// Video API
export const videoApi = {
  upload: (file: File, onProgress?: (progress: number) => void) => {
    const formData = new FormData()
    formData.append('file', file)

    return api.post<ApiResponse<UploadResponse>>('/video/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percentage = (progressEvent.loaded * 100) / progressEvent.total
          onProgress(percentage)
        }
      },
    })
  },

  getInfo: (filename: string) =>
    api.get<ApiResponse<VideoInfo>>(`/video/info/${filename}`),

  download: (filename: string) =>
    api.get(`/video/download/${filename}`, { responseType: 'blob' }),

  listVideos: () =>
    api.get<ApiResponse<string[]>>('/video/list'),

  getFrame: (filename: string, frameNumber?: number) =>
    api.get<Blob>(`/video/frame/${filename}${frameNumber !== undefined ? `?frame_number=${frameNumber}` : ''}`, { responseType: 'blob' }),
}

// Tracking API
export const trackingApi = {
  listModels: () =>
    api.get<ApiResponse<string[]>>('/tracking/models'),

  uploadModel: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post<ApiResponse<UploadResponse>>('/tracking/models/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  startTracking: (params: {
    video_filename: string
    model_name: string
    rois: ROIPreset
    confidence_threshold: number
    iou_threshold: number
    inference_size?: number
    sam_prompt?: string
  }) =>
    api.post<ApiResponse<{ task_id: string }>>('/tracking/start', params),

  getProgress: (taskId: string) =>
    api.get<ApiResponse<ProcessingProgress>>(`/tracking/progress/${taskId}`),

  stopTracking: (taskId: string) =>
    api.post<ApiResponse<void>>(`/tracking/stop/${taskId}`),

  downloadResults: (taskId: string) =>
    api.get(`/tracking/results/${taskId}`, { responseType: 'blob' }),

  prepareBatchDownload: (data: { task_ids: string[]; batch_info: Record<string, unknown> }) =>
    api.post<ApiResponse<{ download_id: string }>>('/tracking/results/batch/prepare', data),

  testDetection: (params: {
    video_filename: string
    model_name: string
    frame_number: number
    confidence_threshold: number
    iou_threshold: number
    inference_size?: number
    rois: ROIPreset
    sam_prompt?: string
  }) =>
    api.post<ApiResponse<{ task_id: string }>>('/tracking/test-detection', params),

  // ROI Templates
  saveROITemplate: (preset: ROIPreset) =>
    api.post<ApiResponse<{ message: string; template_name: string; filename: string }>>(
      '/tracking/roi-templates/save',
      preset
    ),

  listROITemplates: () =>
    api.get<ApiResponse<{
      templates: Array<{
        filename: string
        preset_name: string
        description: string
        timestamp: string
        roi_count: number
      }>
    }>>('/tracking/roi-templates/list'),

  loadROITemplate: (filename: string) =>
    api.get<ApiResponse<ROIPreset>>(`/tracking/roi-templates/load/${filename}`),

  deleteROITemplate: (filename: string) =>
    api.delete<ApiResponse<{ message: string }>>(`/tracking/roi-templates/delete/${filename}`),
}

// ROI Preset API
export const roiApi = {
  listPresets: () =>
    api.get<ApiResponse<string[]>>('/roi/presets'),

  loadPreset: (name: string) =>
    api.get<ApiResponse<ROIPreset>>(`/roi/presets/${name}`),

  savePreset: (preset: ROIPreset) =>
    api.post<ApiResponse<void>>('/roi/presets', preset),

  deletePreset: (name: string) =>
    api.delete<ApiResponse<void>>(`/roi/presets/${name}`),
}

// Analysis API
export const analysisApi = {
  loadLargeJson: (filePath: string) =>
    api.get<ApiResponse<TrackingData>>('/analysis/load-large-json', { params: { file_path: filePath } }),

  uploadLargeJson: (file: File, onProgress?: (progress: number) => void) => {
    const formData = new FormData()
    formData.append('file', file)

    return api.post<ApiResponse<TrackingData>>('/analysis/upload-large-json', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600000, // 10 minutes for very large files
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percentage = (progressEvent.loaded * 100) / progressEvent.total
          onProgress(percentage)
        }
      },
    })
  },

  generateHeatmap: (params: { tracking_data: TrackingData
    settings: HeatmapSettings
  }) =>
    api.post<Blob>('/analysis/heatmap', params, { responseType: 'blob' }),

  analyzeMovement: (trackingData: TrackingData) =>
    api.post<Blob>('/analysis/movement', trackingData, { responseType: 'blob' }),

  generateCompleteAnalysis: (params: {
    tracking_data: TrackingData
    settings: HeatmapSettings
    options?: {
      heatmap?: boolean
      velocity?: boolean
      activity_classification?: boolean
      velocity_display?: {
        show_instantaneous?: boolean
        show_moving_average?: boolean
      }
      heatmap_display?: {
        show_heatmap_only?: boolean
        show_with_overlay?: boolean
      }
      trajectory?: {
        show_trajectory?: boolean
        color?: 'white' | 'black' | 'gray' | 'red' | 'blue'
        width?: number
        alpha?: number
      }
    }
    video_frame_base64?: string
  }) =>
    api.post<Blob>('/analysis/complete', params, { responseType: 'blob' }),

  downloadCompleteAnalysis: (params: {
    tracking_data: TrackingData
    settings: HeatmapSettings
    options?: {
      heatmap?: boolean
      velocity?: boolean
      activity_classification?: boolean
      velocity_display?: {
        show_instantaneous?: boolean
        show_moving_average?: boolean
      }
      heatmap_display?: {
        show_heatmap_only?: boolean
        show_with_overlay?: boolean
      }
      trajectory?: {
        show_trajectory?: boolean
        color?: 'white' | 'black' | 'gray' | 'red' | 'blue'
        width?: number
        alpha?: number
      }
    }
    video_frame_base64?: string
  }) =>
    api.post<Blob>('/analysis/download', params, { responseType: 'blob' }),

  analyzeOpenField: (params: {
    tracking_data: TrackingData
    arena_center_x: number
    arena_center_y: number
    arena_radius: number
  }) =>
    api.post<ApiResponse<any>>('/analysis/open-field', params),

  exportVideo: (params: {
    video_filename: string
    tracking_data: TrackingData
    show_heatmap: boolean
    show_info_panel: boolean
  }) =>
    api.post<Blob>('/analysis/export-video', params, { responseType: 'blob' }),
}

// System API
export const systemApi = {
  checkGPU: () =>
    api.get<ApiResponse<{
      cuda_available: boolean
      mps_available: boolean
      device: string
    }>>('/system/gpu'),

  testYOLO: (modelName: string) =>
    api.post<ApiResponse<{
      gpu_time: number
      cpu_time: number
      speedup: number
    }>>('/system/test-yolo', { model_name: modelName }),

  browse: (path: string = '') =>
    api.get<ApiResponse<{
      current_path: string
      parent: string | null
      home: string
      directories: { name: string; writable: boolean }[]
      writable: boolean
    }>>(`/system/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`),
}

export const experimentApi = {
  start: (req: ExperimentStartRequest) =>
    api.post<ApiResponse<{ exp_id: string; ws_url: string }>>('/experiment/start', req),
  stop: () => api.post<ApiResponse<{
    exp_id: string
    exp_dir: string
    segments: import('@/types').SegmentInfo[]
  }>>('/experiment/stop'),
  listArtifacts: (expId: string) =>
    api.get<ApiResponse<{
      exp_id: string
      exp_dir: string
      files: import('@/types').ArtifactFile[]
    }>>(`/experiment/artifacts/${expId}`),
  status: () => api.get<ApiResponse<ExperimentStatus>>('/experiment/status'),

  listIntegrations: () =>
    api.get<ApiResponse<{ integrations: Integration[] }>>('/experiment/integrations'),
  createIntegration: (i: Integration) =>
    api.post<ApiResponse<Integration>>('/experiment/integrations', i),
  deleteIntegration: (id: string, force = false) =>
    api.delete<ApiResponse<{ deleted: string }>>(`/experiment/integrations/${id}${force ? '?force=true' : ''}`),
  testIntegration: (id: string) =>
    api.post<ApiResponse<{ ok: boolean; status_code?: number; latency_ms?: number; error?: string }>>(`/experiment/integrations/${id}/test`),
  listSerialPorts: () =>
    api.get<ApiResponse<{ ports: SerialPort[] }>>('/experiment/serial-ports'),

  listTriggers: () =>
    api.get<ApiResponse<{ triggers: TriggerRule[] }>>('/experiment/triggers'),
  createTrigger: (r: TriggerRule) =>
    api.post<ApiResponse<TriggerRule>>('/experiment/triggers', r),
  deleteTrigger: (id: string) =>
    api.delete<ApiResponse<{ deleted: string }>>(`/experiment/triggers/${id}`),

  updateRois: (preset: ROIPreset) =>
    api.post<ApiResponse<{ updated: boolean }>>('/experiment/rois', preset),
  pauseRoiEval: (paused: boolean) =>
    api.post<ApiResponse<{ paused: boolean }>>(`/experiment/rois/pause-eval?paused=${paused}`),

  /** Build a download URL for any segment or fixed file (raw_NNN.mp4 / tracking_NNN.jsonl / events.jsonl / metadata.json). */
  artifactUrl: (expId: string, artifact: string) =>
    `/api/experiment/artifacts/${expId}/${encodeURIComponent(artifact)}`,

  /** Open a WebSocket on /api/experiment/events. Caller manages lifecycle. */
  subscribeEvents: (onEvent: (e: ExperimentEvent) => void, onClose?: () => void): WebSocket => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/api/experiment/events`)
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data) as ExperimentEvent
        onEvent(data)
      } catch {
        // ignore malformed
      }
    }
    if (onClose) ws.onclose = onClose
    return ws
  },
}

export default api
