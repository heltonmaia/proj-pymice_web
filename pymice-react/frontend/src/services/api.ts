import axios from 'axios'
import type {
  ApiResponse,
  UploadResponse,
  VideoInfo,
  TrackingData,
  ROIPreset,
  ProcessingProgress,
  HeatmapSettings,
} from '@/types'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 minutes for long processing tasks
})

// Camera API
export const cameraApi = {
  listDevices: () => api.get<ApiResponse<number[]>>('/camera/devices'),

  startStream: (deviceId: number) =>
    api.post<ApiResponse<string>>('/camera/stream/start', { device_id: deviceId }),

  stopStream: () =>
    api.post<ApiResponse<void>>('/camera/stream/stop'),

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
  }) =>
    api.post<ApiResponse<{ task_id: string }>>('/tracking/start', params),

  getProgress: (taskId: string) =>
    api.get<ApiResponse<ProcessingProgress>>(`/tracking/progress/${taskId}`),

  stopTracking: (taskId: string) =>
    api.post<ApiResponse<void>>(`/tracking/stop/${taskId}`),

  downloadResults: (taskId: string) =>
    api.get(`/tracking/results/${taskId}`, { responseType: 'blob' }),

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
  generateHeatmap: (params: {
    tracking_data: TrackingData
    settings: HeatmapSettings
  }) =>
    api.post<Blob>('/analysis/heatmap', params, { responseType: 'blob' }),

  analyzeMovement: (trackingData: TrackingData) =>
    api.post<Blob>('/analysis/movement', trackingData, { responseType: 'blob' }),

  generateCompleteAnalysis: (params: {
    tracking_data: TrackingData
    settings: HeatmapSettings
  }) =>
    api.post<Blob>('/analysis/complete', params, { responseType: 'blob' }),

  downloadCompleteAnalysis: (params: {
    tracking_data: TrackingData
    settings: HeatmapSettings
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
}

export default api
