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
    centroid_x: float
    centroid_y: float
    roi: Optional[str] = None
    detection_method: Literal["yolo", "template"]


class TrackingData(BaseModel):
    video_name: str
    experiment_type: str
    timestamp: str
    total_frames: int
    frames_without_detection: int
    yolo_detections: int
    template_detections: int
    rois: List[ROI]
    tracking_data: List[TrackingFrame]


class TrackingRequest(BaseModel):
    video_filename: str
    model_name: str
    rois: ROIPreset
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    iou_threshold: float = Field(ge=0.0, le=1.0)


class ProcessingProgress(BaseModel):
    current_frame: int
    total_frames: int
    percentage: float
    status: Literal["processing", "completed", "error"]


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
