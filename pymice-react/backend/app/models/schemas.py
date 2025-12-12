"""Pydantic schemas for API request/response validation"""

from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field


# Base Response
class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


# ROI Models
class RectangleROI(BaseModel):
    roi_type: Literal["Rectangle"]
    center_x: float
    center_y: float
    width: float
    height: float


class CircleROI(BaseModel):
    roi_type: Literal["Circle"]
    center_x: float
    center_y: float
    radius: float


class PolygonROI(BaseModel):
    roi_type: Literal["Polygon"]
    center_x: float
    center_y: float
    vertices: List[List[float]]


ROI = Union[RectangleROI, CircleROI, PolygonROI]


class ROIPreset(BaseModel):
    preset_name: str
    description: str
    timestamp: str
    frame_width: int
    frame_height: int
    rois: List[ROI]


# Tracking Models
class TrackingFrame(BaseModel):
    frame_number: int
    centroid_x: Optional[float] = None
    centroid_y: Optional[float] = None
    roi: Optional[str] = None
    roi_index: Optional[int] = None
    detection_method: Literal["yolo", "template", "none"]
    timestamp_sec: float
    bbox: Optional[List[float]] = None
    confidence: Optional[float] = None
    keypoints: Optional[List[dict]] = None
    mask: Optional[List[List[float]]] = None


class VideoInfo(BaseModel):
    total_frames: int
    fps: float
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    duration_sec: Optional[float] = None
    codec: Optional[str] = None
    ffprobe_duration: Optional[float] = None


class TrackingStatistics(BaseModel):
    frames_without_detection: int
    yolo_detections: int
    template_detections: int
    detection_rate: float


class TrackingData(BaseModel):
    video_name: str
    experiment_type: Optional[str] = None
    timestamp: str
    video_info: VideoInfo
    statistics: TrackingStatistics
    rois: List[ROI]
    tracking_data: List[TrackingFrame]


class TrackingRequest(BaseModel):
    video_filename: str
    model_name: str
    rois: ROIPreset
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    iou_threshold: float = Field(ge=0.0, le=1.0)
    inference_size: int = Field(default=640, ge=320, le=1280)  # YOLO inference image size (smaller = less GPU memory)


class ProcessingProgress(BaseModel):
    current_frame: int
    total_frames: int
    percentage: float
    status: Literal["processing", "completed", "error", "stopped"]
    device: Optional[str] = None


# Video Models
class VideoInfo(BaseModel):
    filename: str
    width: int
    height: int
    fps: float
    total_frames: int
    duration: float


class UploadResponse(BaseModel):
    filename: str
    path: str
    size: int


# Camera Models
class CameraSettings(BaseModel):
    device_id: int
    resolution: dict = {"width": 640, "height": 480}
    fps: int = 30


class StreamRequest(BaseModel):
    device_id: int


class RecordingRequest(BaseModel):
    device_id: int
    filename: Optional[str] = None


# Analysis Models
class HeatmapSettings(BaseModel):
    resolution: int = Field(ge=20, le=100)
    colormap: Literal["hot", "viridis", "plasma", "jet", "rainbow", "coolwarm"]
    transparency: float = Field(ge=0.0, le=1.0)
    movement_threshold_percentile: int = Field(default=75, ge=50, le=95)
    velocity_bins: int = Field(default=50, ge=20, le=100)
    gaussian_sigma: float = Field(default=1.0, ge=0.0, le=3.0)
    moving_average_window: int = Field(default=30, ge=5, le=200)


class HeatmapRequest(BaseModel):
    tracking_data: TrackingData
    settings: HeatmapSettings


class OpenFieldAnalysisRequest(BaseModel):
    tracking_data: TrackingData
    arena_center_x: float
    arena_center_y: float
    arena_radius: float


class VideoExportRequest(BaseModel):
    video_filename: str
    tracking_data: TrackingData
    show_heatmap: bool = True
    show_info_panel: bool = True


# System Models
class GPUStatus(BaseModel):
    cuda_available: bool
    mps_available: bool
    device: str


class YOLOTestResult(BaseModel):
    gpu_time: float
    cpu_time: float
    speedup: float
