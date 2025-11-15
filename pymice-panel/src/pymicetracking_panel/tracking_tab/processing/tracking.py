"""
Frame processing and tracking functions
"""

import traceback

import cv2 as cv
import numpy as np
# Try to import with GPU support, fallback to CPU
try:
    import torch
    GPU_TORCH_AVAILABLE = True
except ImportError:
    # Mock for CPU-only mode
    class torch:
        @staticmethod
        def no_grad():
            class NoGradContext:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return NoGradContext()
    GPU_TORCH_AVAILABLE = False

from ultralytics import YOLO

from .detection import calculate_centroid, template_matching

COLORS = {
    "mask": (255, 165, 0),  # Orange (YOLO detection)
    "centroid": (0, 255, 255),  # Yellow (YOLO centroid)
    "template_mask": (0, 255, 0),  # Green (Template detection)
    "template_centroid": (255, 0, 255),  # Purple (Template centroid)
    "text": (255, 255, 255),  # White
    "roi_rectangle": (255, 0, 255), # Magenta - highly visible on both black and white
    "roi_circle": (0, 255, 0),
    "roi_polygon": (100,0,0),
}

                
    
def create_roi_mask(rois: list, frame_shape: tuple[int, int]) -> np.ndarray:
    """
    Cria uma máscara binária a partir dos ROIs definidos.
    Args:
        rois: lista de objetos ROI (Rectangle ou Circle)
        frame_shape: shape do frame em cinza (altura, largura)
    Returns:
        np.ndarray: máscara binária (uint8)
    """
    mask = np.zeros(frame_shape, dtype=np.uint8)

    height, width = frame_shape

    for roi in rois:
        if str(type(roi)) == "<class 'bokeh.models.annotations.geometry.BoxAnnotation'>":
            x0, y0, x1, y1 = list(map(int, [roi.left, height-roi.top, roi.right, height-roi.bottom]))
            
            cv.rectangle(mask, (x0, y0), (x1, y1), 255, -1)

        elif str(type(roi)) == "<class 'bokeh.models.renderers.glyph_renderer.GlyphRenderer'>":            
            pass
            # cv.circle(mask, (int(roi.glyph.x), height-int(roi.glyph.y)), int(roi.glyph.radius), 255, -1)
        
        elif str(type(roi)) == "<class 'bokeh.models.annotations.geometry.PolyAnnotation'>":
            fixed_ys = [height-i for i in roi.ys]
            
            pts = np.array(list(zip(map(int, roi.xs), map(int, fixed_ys))), np.int32)
            pts = pts.reshape((-1,1,2))
            cv.polylines(mask, [pts], True, (0,255,255))

    return mask

def draw_rois(image: np.ndarray, rois: list, circle_data: dict = None):
    height, _, _ = image.shape

    for roi in rois:
        if str(type(roi)) == "<class 'bokeh.models.annotations.geometry.BoxAnnotation'>":
            x0, y0, x1, y1 = list(map(int, [roi.left, height-roi.top, roi.right, height-roi.bottom]))
            cv.rectangle(image, (x0, y0), (x1, y1), COLORS["roi_rectangle"], 2)

        elif str(type(roi)) == "<class 'bokeh.models.renderers.glyph_renderer.GlyphRenderer'>":  
            try:
                # Use the saved circle data if available
                roi_id = id(roi)
                if circle_data and roi_id in circle_data:
                    # Use the exact values saved during circle creation
                    data = circle_data[roi_id]
                    center_x = int(data['center_x'])
                    center_y = int(data['center_y'])
                    radius = int(data['radius'])
                    
                elif 'x' in roi.data_source.data and 'y' in roi.data_source.data:
                    # Fallback to data source parsing
                    center_x = int(roi.data_source.data['x'][0])
                    center_y = int(roi.data_source.data['y'][0])
                    if 'size' in roi.data_source.data:
                        size_value = roi.data_source.data['size'][0]
                        radius = int(size_value / 2)
                    else:
                        radius = 10
                else:
                    # Fallback to old format
                    center_x = int(roi.glyph.x)
                    center_y = int(roi.glyph.y)
                    radius = int(roi.glyph.radius)
                    
                # Draw circle similar to Bokeh: filled with transparency + outline
                cv.circle(image, (center_x, height - center_y), radius, COLORS["roi_circle"], 2)
                # Add slight fill for better visibility (similar to Bokeh alpha=0.3)
                overlay = image.copy()
                cv.circle(overlay, (center_x, height - center_y), radius, COLORS["roi_circle"], -1)
                cv.addWeighted(overlay, 0.1, image, 0.9, 0, image)
            except (AttributeError, KeyError, ValueError, TypeError) as e:
                print(f"Error drawing circle ROI: {e}")
    
        elif str(type(roi)) == "<class 'bokeh.models.annotations.geometry.PolyAnnotation'>":
            fixed_ys = [height-i for i in roi.ys]
        
            pts = np.array(list(zip(map(int, roi.xs), map(int, fixed_ys))), np.int32)
            pts = pts.reshape((-1,1,2))
            cv.polylines(image, [pts], True, COLORS["roi_polygon"], 2)

    return image

def process_frame(frame: np.ndarray, model: YOLO, frame_num: int, params) -> np.ndarray:
    """
    Process a single frame for mouse detection and ROI tracking.

    Args:
        frame: Input frame (RGB format)
        model: YOLO model for detection
        frame_num: Frame number for tracking

    Returns:
        np.ndarray: Processed frame with overlays
    """
    try:
        overlay = frame.copy()
        frame_height, frame_width = frame.shape[:2]
        centroid = None
        current_roi = None
        detection_made = False

        # Initialize tracking data for this frame
        frame_data = {
            "frame_number": frame_num,
            "centroid_x": None,
            "centroid_y": None,
            "roi": None,
            "detection_method": None,
        }

        # First try YOLO detection
        if GPU_TORCH_AVAILABLE:
            with torch.no_grad():
                results = model(
                    frame,
                    verbose=False,
                    conf=params.slider_confidence.value,
                    iou=params.slider_iou.value,
                    device=params.device,
                    imgsz=640,
                )
        else:
            # CPU-only mode without torch context
            results = model(
                frame,
                verbose=False,
                conf=params.slider_confidence.value,
                iou=params.slider_iou.value,
                device=params.device,
                imgsz=640,
            )

        if results and len(results) > 0:
            if (
                hasattr(results[0], "masks")
                and results[0].masks is not None
                and len(results[0].masks) > 0
                and hasattr(results[0], "boxes")
                and results[0].boxes is not None
                and len(results[0].boxes.conf) > 0
            ):
                # Ensure we don't access beyond available masks
                conf_array = results[0].boxes.conf.cpu().numpy()
                num_masks = len(results[0].masks.data)
                
                # Only consider confidences for available masks
                if len(conf_array) > num_masks:
                    conf_array = conf_array[:num_masks]
                
                if len(conf_array) > 0:
                    best_idx = np.argmax(conf_array)
                    
                    if best_idx < num_masks:
                        best_mask_tensor = results[0].masks.data[best_idx].cpu()

                        best_mask = cv.resize(
                            best_mask_tensor.numpy(),
                            (frame_width, frame_height),
                            interpolation=cv.INTER_NEAREST,
                        )

                        binary_mask = (best_mask > 0.5).astype(np.uint8)
                        centroid = calculate_centroid(binary_mask)

                        if centroid:
                            detection_made = True
                            params.yolo_detections += 1

                            frame_data.update(
                                {
                                    "centroid_x": centroid[0],
                                    "centroid_y": centroid[1],
                                    "detection_method": "YOLO",
                                }
                            )

                            colored_mask = np.zeros_like(overlay)
                            if (
                                binary_mask.shape[0] == colored_mask.shape[0]
                                and binary_mask.shape[1] == colored_mask.shape[1]
                            ):
                                colored_mask[binary_mask > 0] = COLORS["mask"]
                                overlay = cv.addWeighted(overlay, 0.7, colored_mask, 0.3, 0)
                                cv.circle(overlay, centroid, 4, COLORS["centroid"], -1)

        # If YOLO didn't detect anything, try template matching
        if not detection_made and params.background_frame is not None:
            current_frame_gray = cv.cvtColor(frame, cv.COLOR_RGB2GRAY)
            # Gere a máscara dos ROIs
            roi_mask = create_roi_mask(params.rois, current_frame_gray.shape)
            centroid = template_matching(
                current_frame_gray, params.background_frame, roi_mask
            )

            if centroid:
                detection_made = True
                params.template_detections += 1

                frame_data.update(
                    {
                        "centroid_x": centroid[0],
                        "centroid_y": centroid[1],
                        "detection_method": "Template",
                    }
                )

                # Draw template detection with different color
                cv.circle(overlay, centroid, 8, COLORS["template_centroid"], 2)
                cv.circle(overlay, centroid, 4, COLORS["template_centroid"], -1)

            
        # Update no detection counter
        if not detection_made:
            params.no_detection_count += 1
            frame_data["detection_method"] = "None"

        # Add frame data to tracking data
        params.tracking_data.append(frame_data)
        params.frame_count += 1

        return overlay

    except Exception as e:
        error_msg = f"Frame {frame_num} error: {str(e)}"
        error_type = f"Error details: {type(e).__name__}"
        print(error_msg)
        print(error_type)
        print(traceback.format_exc())
        
        # Add error to logs if params has the method
        if hasattr(params, '_add_log_message'):
            params._add_log_message(f"{error_msg} ({error_type})", "error")

        return frame
