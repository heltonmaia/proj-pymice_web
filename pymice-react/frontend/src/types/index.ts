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
  detection_method: 'yolo' | 'template';
}

export interface TrackingData {
  video_name: string;
  experiment_type: string;
  timestamp: string;
  total_frames: number;
  frames_without_detection: number;
  yolo_detections: number;
  template_detections: number;
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

// App State
export interface AppTab {
  id: string;
  label: string;
  icon: string;
}
