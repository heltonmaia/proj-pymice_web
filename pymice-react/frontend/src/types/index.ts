// ROI Types
export type ROIType = 'Rectangle' | 'Circle' | 'Polygon';

export interface BaseROI {
  roi_type: ROIType;
  center_x: number;
  center_y: number;
}

export interface RectangleROI extends BaseROI {
  roi_type: 'Rectangle';
  width: number;
  height: number;
}

export interface CircleROI extends BaseROI {
  roi_type: 'Circle';
  radius: number;
}

export interface PolygonROI extends BaseROI {
  roi_type: 'Polygon';
  vertices: [number, number][];
}

export type ROI = RectangleROI | CircleROI | PolygonROI;

// ROI Preset
export interface ROIPreset {
  preset_name: string;
  description: string;
  timestamp: string;
  frame_width: number;
  frame_height: number;
  rois: ROI[];
}

// Tracking Data
export interface TrackingFrame {
  frame_number: number;
  centroid_x: number;
  centroid_y: number;
  roi: string | null;
  roi_index: number | null;
  detection_method: 'yolo' | 'template';
  timestamp_sec: number;
}

export interface VideoInfo {
  total_frames: number;
  fps: number;
  frame_width?: number;
  frame_height?: number;
  duration_sec?: number;
  codec?: string;
  ffprobe_duration?: number;
}

export interface TrackingStatistics {
  frames_without_detection: number;
  yolo_detections: number;
  template_detections: number;
  detection_rate: number;
}

export interface TrackingData {
  video_name: string;
  experiment_type?: string;
  timestamp: string;
  video_info: VideoInfo;
  statistics: TrackingStatistics;
  rois: ROI[];
  tracking_data: TrackingFrame[];
}

// Camera Settings
export interface CameraSettings {
  device_id: number;
  resolution: {
    width: number;
    height: number;
  };
  fps: number;
}

// Detection Settings
export interface DetectionSettings {
  model_path: string;
  confidence_threshold: number;
  iou_threshold: number;
}

// Analysis Settings
export interface HeatmapSettings {
  resolution: number;
  colormap: 'hot' | 'viridis' | 'plasma' | 'jet' | 'rainbow' | 'coolwarm';
  transparency: number;
  movement_threshold_percentile?: number;
  velocity_bins?: number;
  gaussian_sigma?: number;
  moving_average_window?: number;
}

// API Response Types
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface UploadResponse {
  filename: string;
  path: string;
  size: number;
}

export interface ProcessingProgress {
  current_frame: number;
  total_frames: number;
  percentage: number;
  status: 'processing' | 'completed' | 'error';
  error?: string;
  device?: string;
}

// Video Info
export interface VideoInfo {
  filename: string;
  width: number;
  height: number;
  fps: number;
  total_frames: number;
  duration: number;
}

// Batch Processing
export interface VideoItem {
  file: File
  filename: string
  status: 'pending' | 'uploading' | 'tracking' | 'completed' | 'error'
  progress: number
  result?: any
  error?: string
  uploadedFilename?: string
  taskId?: string
}

// App State
export interface AppTab {
  id: string;
  label: string;
  icon: string;
}
