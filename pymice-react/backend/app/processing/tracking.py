"""YOLO tracking and ROI processing"""

import cv2
import numpy as np
from typing import Optional, List, Dict, Any
from ultralytics import YOLO

from app.models.schemas import ROI
from app.processing.detection import calculate_centroid, template_matching

Point = tuple[int, int]


def create_roi_mask(rois: List[ROI], frame_shape: tuple[int, int]) -> Optional[np.ndarray]:
    """
    Create binary mask from ROI definitions.

    Args:
        rois: List of ROI objects (Rectangle, Circle, or Polygon)
        frame_shape: (height, width) of the video frame

    Returns:
        Binary mask (uint8) with 255 for ROI areas, 0 elsewhere
        Returns None if no ROIs provided
    """
    if not rois:
        return None

    height, width = frame_shape
    mask = np.zeros((height, width), dtype=np.uint8)

    for roi in rois:
        if roi.roi_type == "Rectangle":
            # Rectangle defined by center, width, height
            x1 = int(roi.center_x - roi.width / 2)
            y1 = int(roi.center_y - roi.height / 2)
            x2 = int(roi.center_x + roi.width / 2)
            y2 = int(roi.center_y + roi.height / 2)
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)

        elif roi.roi_type == "Circle":
            # Circle defined by center and radius
            center = (int(roi.center_x), int(roi.center_y))
            radius = int(roi.radius)
            cv2.circle(mask, center, radius, 255, -1)

        elif roi.roi_type == "Polygon":
            # Polygon defined by list of vertices
            points = np.array(roi.vertices, dtype=np.int32)
            cv2.fillPoly(mask, [points], 255)

    return mask


def draw_rois(frame: np.ndarray, rois: List[ROI], color: tuple = (0, 255, 0), thickness: int = 2):
    """
    Draw ROI overlays on frame.

    Args:
        frame: Video frame to draw on (BGR)
        rois: List of ROI objects
        color: BGR color tuple
        thickness: Line thickness
    """
    for roi in rois:
        if roi.roi_type == "Rectangle":
            x1 = int(roi.center_x - roi.width / 2)
            y1 = int(roi.center_y - roi.height / 2)
            x2 = int(roi.center_x + roi.width / 2)
            y2 = int(roi.center_y + roi.height / 2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        elif roi.roi_type == "Circle":
            center = (int(roi.center_x), int(roi.center_y))
            radius = int(roi.radius)
            cv2.circle(frame, center, radius, color, thickness)

        elif roi.roi_type == "Polygon":
            points = np.array(roi.vertices, dtype=np.int32)
            cv2.polylines(frame, [points], True, color, thickness)


def process_frame(
    frame: np.ndarray,
    frame_number: int,
    model: YOLO,
    background_frame: Optional[np.ndarray],
    rois: List[ROI],
    roi_mask: Optional[np.ndarray],
    confidence_threshold: float,
    iou_threshold: float,
    device: str,
) -> Dict[str, Any]:
    """
    Process a single frame with YOLO detection and template matching fallback.

    Args:
        frame: Current video frame (BGR)
        frame_number: Frame index (0-based)
        model: YOLO model instance
        background_frame: Background reference frame (grayscale)
        rois: List of ROI objects
        roi_mask: Binary ROI mask
        confidence_threshold: YOLO confidence threshold (0.0-1.0)
        iou_threshold: YOLO IOU threshold (0.0-1.0)
        device: Device to run inference on ('cuda', 'mps', or 'cpu')

    Returns:
        Dictionary with frame data:
        {
            "frame_number": int,
            "centroid_x": float or None,
            "centroid_y": float or None,
            "roi": str or None,
            "detection_method": "yolo"|"template"|"none"
        }
    """
    centroid: Optional[Point] = None
    detection_method = "none"

    # Try YOLO detection first
    try:
        results = model(
            frame,
            verbose=False,
            conf=confidence_threshold,
            iou=iou_threshold,
            device=device,
            imgsz=640,
        )

        # Check if we got any detections with masks
        if len(results) > 0 and results[0].masks is not None:
            # Get the detection with highest confidence
            masks = results[0].masks.data.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()

            if len(confidences) > 0:
                best_idx = np.argmax(confidences)
                mask = masks[best_idx]

                # Resize mask to frame size
                mask_resized = cv2.resize(mask, (frame.shape[1], frame.shape[0]))

                # Threshold mask to binary
                binary_mask = (mask_resized > 0.5).astype(np.uint8) * 255

                # Calculate centroid from mask
                centroid = calculate_centroid(binary_mask)

                if centroid is not None:
                    detection_method = "yolo"

    except Exception as e:
        print(f"YOLO detection failed for frame {frame_number}: {e}")

    # Fallback to template matching if YOLO failed
    if centroid is None and background_frame is not None:
        try:
            centroid = template_matching(
                frame,
                background_frame,
                roi_mask=roi_mask,
                threshold=25,
            )

            if centroid is not None:
                detection_method = "template"

        except Exception as e:
            print(f"Template matching failed for frame {frame_number}: {e}")

    # Determine which ROI the centroid is in (if any)
    roi_name = None
    if centroid is not None and roi_mask is not None:
        x, y = centroid
        if 0 <= y < roi_mask.shape[0] and 0 <= x < roi_mask.shape[1]:
            if roi_mask[y, x] > 0:
                # Centroid is within an ROI
                # For simplicity, we'll just mark it as "roi_1", "roi_2", etc.
                # In a full implementation, you'd track which specific ROI
                for idx, roi in enumerate(rois):
                    roi_name = f"roi_{idx}"
                    break

    return {
        "frame_number": frame_number,
        "centroid_x": float(centroid[0]) if centroid else None,
        "centroid_y": float(centroid[1]) if centroid else None,
        "roi": roi_name,
        "detection_method": detection_method,
    }


def calculate_background(video_path: str, sample_frames: int = 200) -> Optional[np.ndarray]:
    """
    Calculate median background frame from video.

    Args:
        video_path: Path to video file
        sample_frames: Number of frames to sample (default: 200)

    Returns:
        Grayscale background frame (uint8) or None if failed
    """
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        return None

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_step = max(1, total_frames // sample_frames)

    frames = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frames.append(gray.astype(np.float32))

            if len(frames) >= sample_frames:
                break

        frame_idx += 1

    cap.release()

    if not frames:
        return None

    # Calculate median/average background
    background = np.median(np.array(frames), axis=0).astype(np.uint8)

    return background
