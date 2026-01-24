"""YOLO tracking and ROI processing"""

import cv2
import numpy as np
import torch
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

def point_in_roi(point: Point, roi: ROI) -> bool:
    """
    Check if a point is inside an ROI.

    Args:
        point: (x, y) coordinates
        roi: ROI object

    Returns:
        True if point is inside ROI, False otherwise
    """
    x, y = point

    if roi.roi_type == "Rectangle":
        x1 = int(roi.center_x - roi.width / 2)
        y1 = int(roi.center_y - roi.height / 2)
        x2 = int(roi.center_x + roi.width / 2)
        y2 = int(roi.center_y + roi.height / 2)
        return x1 <= x <= x2 and y1 <= y <= y2

    elif roi.roi_type == "Circle":
        center_x = int(roi.center_x)
        center_y = int(roi.center_y)
        radius = int(roi.radius)
        distance = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        return distance <= radius

    elif roi.roi_type == "Polygon":
        points = np.array(roi.vertices, dtype=np.int32)
        # Use OpenCV's pointPolygonTest
        result = cv2.pointPolygonTest(points, (float(x), float(y)), False)
        return result >= 0

    return False


def get_roi_containing_point(point: Point, rois: List[ROI]) -> Optional[int]:
    """
    Find which ROI contains a point. Suppose last ROIS have a priority over firstly drawn

    Args:
        point: (x, y) coordinates
        rois: List of ROI objects

    Returns:
        Index of ROI containing the point, or None if not in any ROI
    """
    
    idx = list(range(len(rois)))[::-1]
    elements = list(zip(idx, rois[::-1]))

    for idx, roi in elements: #enumerate(rois[::-1]):   
        if point_in_roi(point, roi):
            return idx
            
    return None


def draw_rois(frame: np.ndarray, rois: List[ROI], color: tuple = (0, 255, 0),
              thickness: int = 2, active_roi_index: Optional[int] = None):
    """
    Draw ROI overlays on frame.

    Args:
        frame: Video frame to draw on (BGR)
        rois: List of ROI objects
        color: BGR color tuple for normal ROIs
        thickness: Line thickness
        active_roi_index: Index of the ROI currently containing the animal (will be highlighted)
    """
    for idx, roi in enumerate(rois):
        # Use brighter color for active ROI
        roi_color = (0, 255, 255) if idx == active_roi_index else color  # Yellow for active, green for inactive

        if roi.roi_type == "Rectangle":
            x1 = int(roi.center_x - roi.width / 2)
            y1 = int(roi.center_y - roi.height / 2)
            x2 = int(roi.center_x + roi.width / 2)
            y2 = int(roi.center_y + roi.height / 2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), roi_color, thickness)

        elif roi.roi_type == "Circle":
            center = (int(roi.center_x), int(roi.center_y))
            radius = int(roi.radius)
            cv2.circle(frame, center, radius, roi_color, thickness)

        elif roi.roi_type == "Polygon":
            points = np.array(roi.vertices, dtype=np.int32)
            cv2.polylines(frame, [points], True, roi_color, thickness)


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
    inference_size: int = 640,
    model_name: str = "",
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
        inference_size: YOLO inference image size (default: 640, smaller = less GPU memory)
        model_name: Name of the YOLO model file (to detect seg/pose types)

    Returns:
        Dictionary with frame data:
        {
            "frame_number": int,
            "centroid_x": float or None,
            "centroid_y": float or None,
            "roi": str or None,
            "detection_method": "yolo"|"template"|"none",
            "mask": list of mask points (if segmentation model),
            "keypoints": list of keypoints (if pose model)
        }
    """
    centroid: Optional[Point] = None
    detection_method = "none"
    mask_data = None
    keypoints_data = None

    # Detect model type from filename
    is_seg_model = model_name.lower().endswith('seg.pt')
    is_pose_model = model_name.lower().endswith('pose.pt')

    # Try YOLO detection first
    try:
        # Use torch.no_grad() to prevent memory accumulation
        with torch.no_grad():
            results = model(
                frame,
                verbose=False,
                conf=confidence_threshold,
                iou=iou_threshold,
                device=device,
                imgsz=inference_size,
                half=True if device == "cuda" else False,  # Use FP16 on CUDA to save memory
            )

            # Check if we got any detections
            if len(results) > 0:
                boxes = results[0].boxes

                if boxes is not None and len(boxes) > 0:
                    confidences = boxes.conf.cpu().numpy()
                    best_idx = np.argmax(confidences)

                    # Process segmentation masks
                    if is_seg_model and results[0].masks is not None:
                        masks = results[0].masks.data.cpu().numpy()

                        if len(masks) > 0:
                            mask = masks[best_idx]

                            # Resize mask to frame size
                            mask_resized = cv2.resize(mask, (frame.shape[1], frame.shape[0]))

                            # Threshold mask to binary
                            binary_mask = (mask_resized > 0.5).astype(np.uint8) * 255

                            # Calculate centroid from mask
                            centroid = calculate_centroid(binary_mask)

                            if centroid is not None:
                                detection_method = "yolo"

                                # Save mask contours for visualization
                                contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                                if contours:
                                    # Get largest contour
                                    largest_contour = max(contours, key=cv2.contourArea)
                                    # Simplify contour and convert to list of points
                                    epsilon = 0.005 * cv2.arcLength(largest_contour, True)
                                    approx = cv2.approxPolyDP(largest_contour, epsilon, True)
                                    mask_data = approx.reshape(-1, 2).tolist()

                    # Process pose keypoints
                    elif is_pose_model and results[0].keypoints is not None:
                        keypoints = results[0].keypoints.data.cpu().numpy()

                        if len(keypoints) > 0:
                            kpts = keypoints[best_idx]  # Shape: (num_keypoints, 3) - x, y, confidence

                            # Calculate centroid from visible keypoints
                            visible_kpts = kpts[kpts[:, 2] > 0.5]  # Filter by confidence
                            if len(visible_kpts) > 0:
                                centroid = (
                                    int(np.mean(visible_kpts[:, 0])),
                                    int(np.mean(visible_kpts[:, 1]))
                                )
                                detection_method = "yolo"

                                # Save all keypoints with confidence > 0.3
                                keypoints_data = [
                                    {"x": float(kpt[0]), "y": float(kpt[1]), "conf": float(kpt[2])}
                                    for kpt in kpts if kpt[2] > 0.3
                                ]

                    # Process regular detection (bbox only)
                    elif not is_seg_model and not is_pose_model:
                        # Use bounding box center as centroid
                        box = boxes.xyxy[best_idx].cpu().numpy()
                        x1, y1, x2, y2 = box
                        centroid = (int((x1 + x2) / 2), int((y1 + y2) / 2))
                        detection_method = "yolo"

            # Clear GPU cache periodically to prevent memory buildup
            if device == "cuda" and frame_number % 50 == 0:
                torch.cuda.empty_cache()

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
    roi_index = None
    roi_name = None
    if centroid is not None and rois:
        roi_index = get_roi_containing_point(centroid, rois)
        if roi_index is not None:
            roi_name = f"roi_{roi_index}"

    result = {
        "frame_number": frame_number,
        "centroid_x": float(centroid[0]) if centroid else None,
        "centroid_y": float(centroid[1]) if centroid else None,
        "roi": roi_name,
        "roi_index": roi_index,
        "detection_method": detection_method,
    }

    # Add mask data if available (segmentation model)
    if mask_data is not None:
        result["mask"] = mask_data

    # Add keypoints data if available (pose model)
    if keypoints_data is not None:
        result["keypoints"] = keypoints_data

    return result


def calculate_background(video_path: str, sample_frames: int = 200) -> Optional[np.ndarray]:
    """
    Calculate median background frame from video using frames from the middle section.
    This avoids noise from start/end of video (e.g., person placing/removing animal).

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

    # Use middle 50% of video (from 25% to 75%)
    start_frame = int(total_frames * 0.25)
    end_frame = int(total_frames * 0.75)
    middle_frames_count = end_frame - start_frame

    # Calculate step to sample within middle section
    frame_step = max(1, middle_frames_count // sample_frames)

    frames = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Only process frames in the middle section
        if start_frame <= frame_idx <= end_frame:
            if (frame_idx - start_frame) % frame_step == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frames.append(gray.astype(np.float32))

                if len(frames) >= sample_frames:
                    break

        frame_idx += 1

    cap.release()

    if not frames:
        return None

    # Calculate median background
    background = np.median(np.array(frames), axis=0).astype(np.uint8)

    return background
