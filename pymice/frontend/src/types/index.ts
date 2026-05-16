// ROI Types
export type ROIType = 'Rectangle' | 'Circle' | 'Polygon' | 'OpenFieldCircle' | 'OpenFieldRectangle' | 'FullFrame';

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

export interface OpenFieldCircleROI extends BaseROI{
  roi_type: 'OpenFieldCircle';
  min_radius: number;
  max_radius: number;
}

export interface OpenFieldRectangleROI extends BaseROI{
  roi_type: 'OpenFieldRectangle';
}
  

export type ROI = RectangleROI | CircleROI | PolygonROI | OpenFieldCircleROI | OpenFieldRectangleROI | FullFrameROI;;

export interface FullFrameROI extends BaseROI {
  roi_type: 'FullFrame';
}

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
export interface Keypoint {
  x: number;
  y: number;
  conf: number;
}

export interface TrackingFrame {
  frame_number: number;
  centroid_x: number;
  centroid_y: number;
  roi: string | null;
  roi_index: number | null;
  detection_method: 'yolo' | 'template' | 'none';
  timestamp_sec: number;
  bbox?: [number, number, number, number];
  confidence?: number;
  keypoints?: Keypoint[];
  mask?: [number, number][];
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
  inference_size?: number; // YOLO inference image size (320-1280, default: 640)
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
  outlier_filter_enabled?: boolean;
  outlier_filter_k?: number;
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
  status: 'processing' | 'completed' | 'error' | 'stopped';
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

// --- Experiment Recording ---

export type SerialPort = { device: string; description: string; hwid: string }

export type IntegrationKind = 'serial' | 'http'

export interface IntegrationConfigSerial {
  port: string
  baud: number
  newline: string
}

export interface IntegrationConfigHttp {
  base_url: string
  default_method: 'GET' | 'POST' | 'PUT'
  default_timeout_sec: number
  headers: Record<string, string>
}

export interface Integration {
  id: string
  name: string
  kind: IntegrationKind
  config: IntegrationConfigSerial | IntegrationConfigHttp
}

export interface TriggerMatch {
  event_type: 'roi_entry' | 'roi_exit' | 'tick' | 'frame_drop'
  roi_name?: string | null
  min_dwell_sec?: number | null
  cooldown_sec?: number | null
}

export interface TriggerAction {
  integration_id?: string | null
  kind: 'integration' | 'log'
  payload?: string | Record<string, unknown> | null
  label?: string | null
  timeout_sec?: number
}

export interface TriggerRule {
  id: string
  name: string
  match: TriggerMatch
  action: TriggerAction
}

export interface ExperimentStartRequest {
  device_id: number
  model_name: string
  rois: ROIPreset
  confidence_threshold?: number
  iou_threshold?: number
  inference_size?: number
  fps_target?: number | null
  max_consecutive_drops?: number
  triggers?: TriggerRule[]
  output_base_dir?: string
  segment_max_mb?: number
  segment_max_seconds?: number
}

export interface SegmentInfo {
  index: number
  video: string
  tracking: string
  frame_start: number
  frame_end: number | null
  started_at_sec: number
  ended_at_sec: number | null
  bytes: number
}

export interface ArtifactFile {
  name: string
  kind: 'video' | 'tracking' | 'events' | 'metadata' | 'other'
  size: number
}

export interface ExperimentStatus {
  exp_id?: string | null
  state: 'idle' | 'running' | 'stopped' | 'crashed'
  started_at?: string | null
  frames_processed: number
  fps_actual: number
  detections: number
  events_emitted: number
  last_active_roi?: number | null
}

export interface ExperimentEvent {
  type: string
  frame_idx?: number
  t?: number
  // additional fields per type
  [k: string]: unknown
}
