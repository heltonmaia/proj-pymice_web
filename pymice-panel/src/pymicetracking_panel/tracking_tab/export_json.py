import json
from datetime import datetime
from typing import Any


def convert_rois_to_dict(rois: list, circle_roi_data: dict = None, frame_height: int = None) -> list[dict]:
    """Convert ROI objects to dictionary format following the expected JSON structure"""
    result = []
    
    if circle_roi_data is None:
        circle_roi_data = {}

    for roi in rois:
        try:
            roi_type_str = str(type(roi))
            
            # Handle Rectangle ROIs (BoxAnnotation)
            if "BoxAnnotation" in roi_type_str:
                center_x = int((roi.left + roi.right) / 2)
                width = int(roi.right - roi.left)
                # Fix coordinate system issue: ensure height is always positive
                # Bokeh uses bottom-left origin, but we need consistent height values
                height = int(abs(roi.top - roi.bottom))
                
                # Convert Y coordinates from Bokeh (bottom-left origin) to OpenCV (top-left origin)
                if frame_height is not None:
                    center_y = int(frame_height - (roi.bottom + roi.top) / 2)
                else:
                    center_y = int((roi.bottom + roi.top) / 2)
                
                result.append({
                    "center_x": center_x,
                    "center_y": center_y,
                    "width": width,
                    "height": height,
                    "roi_type": "Rectangle"
                })
            
            # Handle Circle ROIs (GlyphRenderer)
            elif "GlyphRenderer" in roi_type_str:
                # Try to get circle data from the stored circle_roi_data
                circle_id = id(roi)
                if circle_id in circle_roi_data:
                    circle_info = circle_roi_data[circle_id]
                    center_x = int(circle_info["center_x"])
                    center_y = int(circle_info["center_y"])
                    
                    # Convert Y coordinate from Bokeh to OpenCV system
                    if frame_height is not None:
                        center_y = int(frame_height - center_y)
                    
                    result.append({
                        "center_x": center_x,
                        "center_y": center_y,
                        "radius": int(circle_info["radius"]),
                        "roi_type": "Circle"
                    })
                else:
                    # Fallback: try to extract from data source
                    if hasattr(roi, 'data_source') and roi.data_source.data:
                        data = roi.data_source.data
                        if "x" in data and "y" in data:
                            center_x = int(data["x"][0]) if data["x"] else 0
                            center_y = int(data["y"][0]) if data["y"] else 0
                            
                            # Convert Y coordinate from Bokeh to OpenCV system
                            if frame_height is not None:
                                center_y = int(frame_height - center_y)
                                
                            radius = int(data.get("size", [20])[0] / 2) if "size" in data else 10
                            result.append({
                                "center_x": center_x,
                                "center_y": center_y,
                                "radius": radius,
                                "roi_type": "Circle"
                            })
                        else:
                            print(f"Warning: Could not extract circle data from GlyphRenderer")
                            result.append({
                                "center_x": 0,
                                "center_y": 0,
                                "radius": 0,
                                "roi_type": "Circle",
                                "error": "Could not extract circle data"
                            })
                    else:
                        print(f"Warning: No data source available for circle ROI")
                        result.append({
                            "center_x": 0,
                            "center_y": 0,
                            "radius": 0,
                            "roi_type": "Circle",
                            "error": "No circle data available"
                        })
            
            # Handle Polygon ROIs (PolyAnnotation)
            elif "PolyAnnotation" in roi_type_str:
                # For polygons, we calculate a center point and store the vertices
                if hasattr(roi, 'xs') and hasattr(roi, 'ys') and roi.xs and roi.ys:
                    center_x = int(sum(roi.xs) / len(roi.xs))
                    center_y = int(sum(roi.ys) / len(roi.ys))
                    
                    # Convert Y coordinates from Bokeh to OpenCV system
                    if frame_height is not None:
                        center_y = int(frame_height - center_y)
                        # Convert all vertices Y coordinates as well
                        vertices = [(int(x), int(frame_height - y)) for x, y in zip(roi.xs, roi.ys)]
                    else:
                        vertices = list(zip(map(int, roi.xs), map(int, roi.ys)))
                    
                    result.append({
                        "center_x": center_x,
                        "center_y": center_y,
                        "vertices": vertices,
                        "roi_type": "Polygon"
                    })
                else:
                    print(f"Warning: Could not extract polygon data")
                    result.append({
                        "center_x": 0,
                        "center_y": 0,
                        "vertices": [],
                        "roi_type": "Polygon",
                        "error": "Could not extract polygon data"
                    })
            else:
                # Fallback for unknown ROI types
                print(f"Warning: Unknown ROI type: {roi_type_str}")
                result.append({
                    "center_x": 0,
                    "center_y": 0,
                    "roi_type": "Unknown",
                    "error": f"Unknown ROI type: {roi_type_str}"
                })
                
        except Exception as e:
            print(f"Warning: Could not convert ROI to dict: {e}")
            result.append({
                "center_x": 0,
                "center_y": 0,
                "roi_type": "Error",
                "error": f"Could not convert ROI: {str(e)}"
            })

    return result


def export_tracking_data(
    video_name: str,
    experiment_type: str,
    total_frames: int,
    frames_without_detection: int,
    yolo_detections: int,
    template_detections: int,
    rois: list,
    tracking_data: list[dict[str, Any]],
    circle_roi_data: dict = None,
    frame_height: int = None,
) -> bytes:
    """
    Export tracking data to JSON format.

    Args:
        - video_name: Name of the processed video
        - experiment_type: Type of experiment
        - total_frames: Total number of frames processed
        - frames_without_detection: Number of frames without detection
        - yolo_detections: Number of YOLO detections
        - template_detections: Number of template matching detections
        - rois: List of ROI objects
        - tracking_data: List of frame tracking data

    Returns:
        bytes: JSON data as bytes
    """

    export_data = {
        "video_name": video_name,
        "experiment_type": experiment_type,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total_frames": total_frames,
        "frames_without_detection": frames_without_detection,
        "yolo_detections": yolo_detections,
        "template_detections": template_detections,
        "rois": convert_rois_to_dict(rois, circle_roi_data, frame_height),
        "tracking_data": tracking_data,
    }

    # Convert to JSON string and then to bytes
    json_string = json.dumps(export_data, indent=2)

    return json_string.encode("utf-8")


def create_download_filename(video_name: str) -> str:
    """
    Create a standardized filename for downloads.

    Args:
        video_name: Original video filename

    Returns:
        str: Formatted filename for download
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    return f"tracking_data_{video_name}_{timestamp}.json"
