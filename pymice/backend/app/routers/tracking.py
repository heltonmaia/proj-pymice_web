"""Tracking API endpoints"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import shutil
import uuid
import json
import io
import gc
import time
import cv2
import numpy as np
import torch
import subprocess
import sys
from datetime import datetime
from PIL import Image
from ultralytics import YOLO

MODEL_DIR = "temp/models"
TRACKING_DIR = "temp/tracking"
ROI_TEMPLATES_DIR = "temp/roi_templates"

# Add temp/models to path to import sam3
models_dir = os.path.abspath(MODEL_DIR)
if models_dir not in sys.path:
    sys.path.append(models_dir)

try:
    from sam3.model_builder import build_sam3_video_model
    SAM3_AVAILABLE = True
except ImportError as e:
    print(f"Warning: sam3 implementation not found in temp/models: {e}")
    SAM3_AVAILABLE = False

from app.models.schemas import (
    ApiResponse,
    TrackingRequest,
    ProcessingProgress,
    UploadResponse,
    ROIPreset
)
from app.processing.tracking import (
    process_frame,
    create_roi_mask,
    calculate_background,
    draw_rois,
    get_roi_containing_point,
    get_gpu_memory_info,
    cleanup_gpu_memory,
)

# GPU memory threshold (percentage) - will cleanup if above this
GPU_MEMORY_THRESHOLD = 80.0

# Minimum free GPU memory in GB before forcing cleanup
MIN_FREE_GPU_MEMORY_GB = 1.0

router = APIRouter()

# Store tracking tasks
tracking_tasks = {}

# Store current tracking frames for live preview
tracking_frames = {}

# Pending batch-download requests (prepare → stream). Entries are one-shot; TTL-purged on prepare.
batch_download_requests: Dict[str, Dict[str, Any]] = {}
BATCH_DOWNLOAD_TTL_SEC = 3600


class BatchDownloadPrepareRequest(BaseModel):
    task_ids: List[str]
    batch_info: Dict[str, Any] = {}


def get_video_info_ffprobe(video_path: str) -> dict:
    """
    Extract video information using ffprobe (part of ffmpeg).

    Args:
        video_path: Path to video file

    Returns:
        Dictionary with video metadata (fps, duration, etc.)
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if video_stream:
                # Parse FPS (can be in different formats like "30/1" or "29.97")
                fps_str = video_stream.get('r_frame_rate', '30/1')
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)

                return {
                    'fps': fps,
                    'duration': float(data.get('format', {}).get('duration', 0)),
                    'width': video_stream.get('width', 0),
                    'height': video_stream.get('height', 0),
                    'codec': video_stream.get('codec_name', 'unknown'),
                }

        return None
    except Exception as e:
        print(f"ffprobe failed: {e}")
        return None


@router.get("/models")
async def list_models():
    """List available YOLO models"""
    print(f"DEBUG: Listing models from {os.path.abspath(MODEL_DIR)}")
    if not os.path.exists(MODEL_DIR):
        print(f"DEBUG: Creating {MODEL_DIR}")
        os.makedirs(MODEL_DIR, exist_ok=True)

    models = [f for f in os.listdir(MODEL_DIR) if f.endswith('.pt')]
    print(f"DEBUG: Found models: {models}")

    return ApiResponse(success=True, data={"models": models})


@router.post("/models/upload")
async def upload_model(file: UploadFile = File(...)):
    """Upload a YOLO model file"""
    try:
        os.makedirs(MODEL_DIR, exist_ok=True)

        if not file.filename.endswith('.pt'):
            raise HTTPException(status_code=400, detail="Only .pt files are allowed")

        filepath = os.path.join(MODEL_DIR, file.filename)

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(filepath)

        return ApiResponse(
            success=True,
            data=UploadResponse(
                filename=file.filename,
                path=filepath,
                size=file_size
            ).model_dump()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def process_sam3_chunk_fast(predictor, frames_pil, frames_cv, prompt, device, task_id, chunk_idx, total_chunks,
                             start_frame_num, total_frames, rois, roi_mask, tracking_data,
                             yolo_detections, template_detections, no_detection_count,
                             preview_skip_frames, jpeg_quality):
    """Process a chunk of frames with SAM3 - FAST single-pass version with live preview"""
    inference_state = None

    try:
        print(f"[Chunk {chunk_idx + 1}/{total_chunks}] Processing {len(frames_pil)} frames...")

        # Initialize inference state with chunk frames
        inference_state = predictor.init_state(
            resource_path=frames_pil,
            offload_video_to_cpu=True,  # Keep frames on CPU to save GPU memory
        )

        # Add text prompt at first frame
        _, out = predictor.add_prompt(
            inference_state=inference_state,
            frame_idx=0,
            text_str=prompt,
            obj_id=1
        )

        num_objects = len(out.get("out_obj_ids", [])) if out else 0
        if num_objects == 0:
            print(f"[Chunk {chunk_idx + 1}/{total_chunks}] No objects detected")
            # Process frames with no detection
            for local_idx, frame_cv in enumerate(frames_cv):
                global_frame_num = start_frame_num + local_idx

                frame_data = {
                    "frame_number": global_frame_num,
                    "centroid_x": None,
                    "centroid_y": None,
                    "detection_method": "none",
                    "mask": None,
                    "roi": None,
                    "roi_index": None,
                    "timestamp_sec": global_frame_num / 30.0,  # Approximate
                }
                tracking_data.append(frame_data)
                no_detection_count[0] += 1

                # Simple preview without detection
                if global_frame_num % preview_skip_frames == 0:
                    vis_frame = frame_cv.copy()
                    cv2.putText(vis_frame, f"Frame: {global_frame_num}/{total_frames}", (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    _, buffer = cv2.imencode('.jpg', vis_frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                    tracking_frames[task_id] = buffer.tobytes()
            return

        print(f"[Chunk {chunk_idx + 1}/{total_chunks}] Detected {num_objects} objects, propagating...")

        # Propagate and visualize in SINGLE PASS
        for local_idx, out in predictor.propagate_in_video(
            inference_state=inference_state,
            start_frame_idx=0,
            max_frame_num_to_track=None,
            reverse=False,
        ):
            global_frame_num = start_frame_num + local_idx
            frame_cv = frames_cv[local_idx]

            # Process detection result
            frame_data = {
                "frame_number": global_frame_num,
                "centroid_x": None,
                "centroid_y": None,
                "detection_method": "none",
                "mask": None,
                "roi": None,
                "roi_index": None,
                "timestamp_sec": global_frame_num / 30.0,
            }

            if out is not None and "out_binary_masks" in out and len(out["out_binary_masks"]) > 0:
                # Get first mask
                mask = out["out_binary_masks"][0]
                if torch.is_tensor(mask):
                    mask_np = mask.cpu().numpy()
                else:
                    mask_np = np.array(mask)

                if len(mask_np.shape) == 3:
                    mask_np = mask_np[0]

                mask_np = (mask_np * 255).astype(np.uint8)

                # Find centroid
                contours, _ = cv2.findContours(mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    max_contour = max(contours, key=cv2.contourArea)
                    M = cv2.moments(max_contour)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        frame_data["centroid_x"] = cx
                        frame_data["centroid_y"] = cy
                        frame_data["detection_method"] = "sam3"

                        # Simplified mask for storage
                        epsilon = 0.01 * cv2.arcLength(max_contour, True)
                        approx = cv2.approxPolyDP(max_contour, epsilon, True)
                        frame_data["mask"] = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]

                        # Check ROI
                        if roi_mask is not None:
                            roi_idx = get_roi_containing_point((cx, cy), roi_mask)
                            if roi_idx is not None and 0 <= roi_idx < len(rois):
                                frame_data["roi"] = rois[roi_idx].name
                                frame_data["roi_index"] = roi_idx

                        yolo_detections[0] += 1
                    else:
                        no_detection_count[0] += 1
                else:
                    no_detection_count[0] += 1
            else:
                no_detection_count[0] += 1

            tracking_data.append(frame_data)

            # Live preview - show every Nth frame
            if global_frame_num % preview_skip_frames == 0:
                vis_frame = frame_cv.copy()

                # Draw ROIs
                if rois:
                    active_roi_index = frame_data.get("roi_index")
                    draw_rois(vis_frame, rois, color=(0, 255, 0), thickness=2, active_roi_index=active_roi_index)

                # Draw detection
                if frame_data["centroid_x"] is not None:
                    cx = int(frame_data["centroid_x"])
                    cy = int(frame_data["centroid_y"])

                    # Draw mask
                    if "mask" in frame_data and frame_data["mask"]:
                        mask_points = np.array(frame_data["mask"], dtype=np.int32)
                        overlay = vis_frame.copy()
                        cv2.fillPoly(overlay, [mask_points], (0, 255, 255))
                        cv2.addWeighted(overlay, 0.3, vis_frame, 0.7, 0, vis_frame)
                        cv2.polylines(vis_frame, [mask_points], True, (0, 255, 255), 2)

                    # Draw centroid
                    cv2.circle(vis_frame, (cx, cy), 10, (0, 0, 255), -1)
                    cv2.circle(vis_frame, (cx, cy), 15, (255, 255, 255), 2)

                    cv2.putText(vis_frame, "Method: sam3", (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                    if frame_data.get("roi"):
                        cv2.putText(vis_frame, f"In {frame_data['roi'].upper()}", (10, 90),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                cv2.putText(vis_frame, f"Frame: {global_frame_num}/{total_frames}", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                # Encode and store
                _, buffer = cv2.imencode('.jpg', vis_frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                tracking_frames[task_id] = buffer.tobytes()

            # Update progress
            tracking_tasks[task_id].update({
                "current_frame": global_frame_num,
                "percentage": (global_frame_num / total_frames) * 100,
            })

    finally:
        # Explicitly clear inference state references
        if inference_state is not None:
            if "cached_features" in inference_state:
                inference_state["cached_features"].clear()
            if "output_dict" in inference_state:
                if "cond_frame_outputs" in inference_state["output_dict"]:
                    inference_state["output_dict"]["cond_frame_outputs"].clear()
                if "non_cond_frame_outputs" in inference_state["output_dict"]:
                    inference_state["output_dict"]["non_cond_frame_outputs"].clear()
            if "input_batch" in inference_state:
                del inference_state["input_batch"]
            inference_state.clear()
            del inference_state

        # Synchronize and clear GPU memory
        if device == "cuda":
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
        gc.collect()


def run_tracking_task(task_id: str, request: TrackingRequest):
    """Background task to run YOLO tracking"""
    model = None  # Track model for cleanup
    cap = None    # Track video capture for cleanup

    try:
        # Detect GPU availability
        if torch.cuda.is_available():
            device = "cuda"
            # Initial GPU cleanup before starting
            cleanup_gpu_memory(force=True)
            mem_info = get_gpu_memory_info()
            print(f"GPU Memory at start: {mem_info['used']:.2f}GB used / {mem_info['total']:.2f}GB total ({mem_info['utilization']:.1f}%)")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        print(f"Using device: {device}")

        tracking_tasks[task_id] = {
            "status": "processing",
            "current_frame": 0,
            "total_frames": 0,
            "percentage": 0,
            "device": device,
        }

        # Open video first because SAM3 needs the video_path
        video_path = os.path.join("temp/videos", request.video_filename)
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {request.video_filename}")

        is_sam3 = False
        sam3_generator = None
        predictor = None

        if 'sam' in request.model_name.lower() and SAM3_AVAILABLE:
            print(f"Initializing SAM3 model for tracking: {request.model_name}")
            is_sam3 = True
            model_path = os.path.join(MODEL_DIR, request.model_name)
            if not os.path.exists(model_path) and request.model_name.lower() == 'sam3':
                model_path = os.path.join(MODEL_DIR, "sam3.pt")

            # Limit GPU memory to prevent crashes
            if device == "cuda":
                try:
                    torch.cuda.set_per_process_memory_fraction(0.85)  # Use max 85% of GPU
                    print("GPU memory limited to 85%")
                except Exception as e:
                    print(f"Warning: Could not limit GPU memory: {e}")

            predictor = build_sam3_video_model(
                checkpoint_path=model_path,
                device=device,
                load_from_HF=False
            )
            print("SAM3 video model loaded")

            # SAM3 chunk processing will be handled in the main loop
            # We don't initialize inference_state here to avoid loading entire video

        else:
            # Load YOLO model with memory-efficient settings
            model_path = os.path.join(MODEL_DIR, request.model_name)
            if not os.path.exists(model_path):
                # Fallback check for sam3 if the model is named sam3 but SAM3 is not available
                if request.model_name == 'sam3':
                    model_path = os.path.join(MODEL_DIR, 'sam3.pt')

                if not os.path.exists(model_path):
                    raise FileNotFoundError(f"Model not found: {request.model_name}")

            model = YOLO(model_path)
            if device == "cuda":
                # Set CUDA memory allocation settings for better memory management
                # This helps prevent memory fragmentation
                if hasattr(torch.cuda, 'set_per_process_memory_fraction'):
                    try:
                        # Limit to 90% of GPU memory to leave headroom
                        torch.cuda.set_per_process_memory_fraction(0.9)
                    except Exception as e:
                        print(f"Could not set memory fraction: {e}")

                model.to("cuda")

                # Log memory after model load
                mem_info = get_gpu_memory_info()
                print(f"GPU Memory after model load: {mem_info['used']:.2f}GB used ({mem_info['utilization']:.1f}%)")

            elif device == "mps":
                model.to("mps")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Failed to open video file")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        if total_frames <= 0:
            print(f"Warning: cap.get(CAP_PROP_FRAME_COUNT) returned 0. Trying to count frames manually...")
            # Try to get total frames by seeking to end if count is 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, 1e9)
            total_frames = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0) # Reset to beginning
            
            if total_frames <= 0:
                raise RuntimeError("Failed to determine video frame count")

        # Get video info using ffprobe
        video_info = get_video_info_ffprobe(video_path)
        if video_info:
            fps = video_info['fps']  # Use ffprobe FPS if available (more accurate)
            print(f"Video info from ffprobe: {fps} fps, {video_info['duration']:.2f}s duration")

        tracking_tasks[task_id]["total_frames"] = total_frames

        # Preview optimization: only encode every Nth frame
        preview_skip_frames = 5  # Only update preview every 5 frames
        jpeg_quality = 70  # Lower quality for faster encoding

        # Initialize a placeholder frame for immediate preview BEFORE any heavy processing
        # Create a simple black frame with "Processing..." text
        placeholder_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
        processing_text = "Processing with SAM3..." if is_sam3 else "Calculating background..."
        cv2.putText(placeholder_frame, processing_text,
                   (frame_width // 2 - 250, frame_height // 2),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
        _, buffer = cv2.imencode('.jpg', placeholder_frame, encode_params)
        tracking_frames[task_id] = buffer.tobytes()

        # Calculate background (only for YOLO, not needed for SAM3)
        background_frame = None
        if not is_sam3:
            print("Calculating background...")
            background_frame = calculate_background(video_path)

        # Create ROI mask
        roi_mask = None
        if request.rois.rois:
            roi_mask = create_roi_mask(request.rois.rois, (frame_height, frame_width))

        # Process frames
        tracking_data = []
        yolo_detections = 0
        template_detections = 0
        no_detection_count = 0

        frame_number = 0

        # SAM3 chunk processing parameters - OPTIMIZED for speed
        SAM3_CHUNK_SIZE = 100  # Larger chunks = faster (was 30)
        SAM3_MAX_DELAY = 2  # Max delay only if needed (was 3)
        GPU_MEMORY_SAFE_THRESHOLD = 75.0  # Only delay if above this %

        if is_sam3:
            # SAM3: Process video in chunks - FAST single-pass version
            print(f"Processing video with SAM3 (FAST mode)")
            print(f"Chunk size: {SAM3_CHUNK_SIZE} frames")
            print(f"Preview: every {preview_skip_frames} frames")

            prompt = request.sam_prompt if hasattr(request, 'sam_prompt') and request.sam_prompt else "mouse"
            print(f"Prompt: '{prompt}'")

            num_chunks = (total_frames + SAM3_CHUNK_SIZE - 1) // SAM3_CHUNK_SIZE
            print(f"Total chunks: {num_chunks}")

            # Counters as lists to pass by reference
            yolo_detections_ref = [0]
            no_detection_ref = [0]

            for chunk_idx in range(num_chunks):
                if tracking_tasks[task_id].get("stopped"):
                    break

                start_frame = chunk_idx * SAM3_CHUNK_SIZE
                end_frame = min(start_frame + SAM3_CHUNK_SIZE, total_frames)
                frames_in_chunk = end_frame - start_frame

                print(f"\n[Chunk {chunk_idx + 1}/{num_chunks}] Frames {start_frame}-{end_frame - 1}")

                # Extract frames for this chunk
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                frames_pil = []
                frames_cv = []

                for _ in range(frames_in_chunk):
                    ret, frame_cv = cap.read()
                    if not ret:
                        break

                    frames_cv.append(frame_cv)

                    # Convert to PIL for SAM3
                    frame_rgb = cv2.cvtColor(frame_cv, cv2.COLOR_BGR2RGB)
                    frames_pil.append(Image.fromarray(frame_rgb))

                if not frames_pil:
                    print(f"[Chunk {chunk_idx + 1}/{num_chunks}] No frames, skipping")
                    continue

                # Process chunk - SINGLE PASS with live preview
                process_sam3_chunk_fast(
                    predictor, frames_pil, frames_cv, prompt, device,
                    task_id, chunk_idx, num_chunks,
                    start_frame, total_frames,
                    request.rois.rois, roi_mask,
                    tracking_data, yolo_detections_ref, [0], no_detection_ref,
                    preview_skip_frames, jpeg_quality
                )

                # Free frames immediately
                frames_pil.clear()
                frames_cv.clear()
                del frames_pil, frames_cv

                # Adaptive delay - only if GPU memory is high
                needs_cooling = False
                if device == "cuda" and chunk_idx < num_chunks - 1:
                    mem_info = get_gpu_memory_info()
                    print(f"[Chunk {chunk_idx + 1}/{num_chunks}] GPU: {mem_info['utilization']:.1f}%")

                    if mem_info['utilization'] > GPU_MEMORY_SAFE_THRESHOLD:
                        needs_cooling = True
                        delay = min(SAM3_MAX_DELAY, (mem_info['utilization'] - GPU_MEMORY_SAFE_THRESHOLD) / 10)
                        print(f"  Cooling {delay:.1f}s (GPU hot)...")
                        time.sleep(delay)
                    else:
                        print(f"  GPU OK, no delay needed")

                # Aggressive cleanup
                if device == "cuda":
                    torch.cuda.empty_cache()
                gc.collect()

            # Update final counters
            yolo_detections = yolo_detections_ref[0]
            no_detection_count = no_detection_ref[0]
            frame_number = len(tracking_data)

        else:
            # YOLO: Original frame-by-frame processing
            # Memory monitoring interval (check every N frames)
            memory_check_interval = 100

            while True:
                if tracking_tasks[task_id].get("stopped"):
                    break

                ret, frame = cap.read()
                if not ret:
                    break

                # Check GPU memory periodically and cleanup if needed
                if device == "cuda" and frame_number % memory_check_interval == 0:
                    mem_info = get_gpu_memory_info()
                    if mem_info['utilization'] > GPU_MEMORY_THRESHOLD or mem_info['free'] < MIN_FREE_GPU_MEMORY_GB:
                        print(f"Frame {frame_number}: High GPU memory usage ({mem_info['utilization']:.1f}%), cleaning up...")
                        cleanup_gpu_memory(force=True)
                        mem_after = get_gpu_memory_info()
                        print(f"After cleanup: {mem_after['utilization']:.1f}% used")

                # Get frame timestamp in seconds from video capture
                timestamp_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

                # Process frame with YOLO and template matching
                frame_data = process_frame(
                    frame=frame,
                    frame_number=frame_number,
                    model=model,
                    background_frame=background_frame,
                    rois=request.rois.rois,
                    roi_mask=roi_mask,
                    confidence_threshold=request.confidence_threshold,
                    iou_threshold=request.iou_threshold,
                    device=device,
                    inference_size=request.inference_size,
                    model_name=request.model_name,
                )

                # Add timestamp information to frame data
                frame_data["timestamp_sec"] = timestamp_sec

                tracking_data.append(frame_data)

                # Update counters
                if frame_data["detection_method"] in ["yolo", "sam3"]:
                    yolo_detections += 1
                elif frame_data["detection_method"] == "template":
                    template_detections += 1
                else:
                    no_detection_count += 1

                # Create visualization frame
                vis_frame = frame.copy()

                # Draw ROIs with active ROI highlighting
                active_roi_index = frame_data.get("roi_index")
                draw_rois(vis_frame, request.rois.rois, color=(0, 255, 0), thickness=2,
                         active_roi_index=active_roi_index)

                # Draw centroid if detected
                if frame_data["centroid_x"] is not None and frame_data["centroid_y"] is not None:
                    cx = int(frame_data["centroid_x"])
                    cy = int(frame_data["centroid_y"])

                    # Draw segmentation mask if available
                    if "mask" in frame_data and frame_data["mask"]:
                        mask_points = np.array(frame_data["mask"], dtype=np.int32)
                        # Draw filled polygon with transparency
                        overlay = vis_frame.copy()
                        cv2.fillPoly(overlay, [mask_points], (0, 255, 255))  # Cyan color
                        cv2.addWeighted(overlay, 0.3, vis_frame, 0.7, 0, vis_frame)
                        # Draw contour
                        cv2.polylines(vis_frame, [mask_points], True, (0, 255, 255), 2)

                    # Draw pose keypoints if available
                    if "keypoints" in frame_data and frame_data["keypoints"]:
                        for i, kpt in enumerate(frame_data["keypoints"]):
                            kx, ky = int(kpt["x"]), int(kpt["y"])
                            conf = kpt["conf"]

                            # Color based on confidence (green = high, yellow = medium, red = low)
                            if conf > 0.7:
                                color = (0, 255, 0)  # Green
                            elif conf > 0.5:
                                color = (0, 255, 255)  # Yellow
                            else:
                                color = (0, 165, 255)  # Orange

                            # Draw keypoint
                            cv2.circle(vis_frame, (kx, ky), 5, color, -1)
                            cv2.circle(vis_frame, (kx, ky), 7, (255, 255, 255), 1)

                            # Draw keypoint index
                            cv2.putText(vis_frame, str(i), (kx + 10, ky),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

                    # Draw centroid as circle (red with white border)
                    cv2.circle(vis_frame, (cx, cy), 10, (0, 0, 255), -1)
                    cv2.circle(vis_frame, (cx, cy), 15, (255, 255, 255), 2)

                    # Draw detection method text
                    method_text = f"Method: {frame_data['detection_method']}"
                    cv2.putText(vis_frame, method_text, (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                    # Draw ROI info if animal is in a ROI
                    if frame_data.get("roi"):
                        roi_text = f"In {frame_data['roi'].upper()}"
                        cv2.putText(vis_frame, roi_text, (10, 90),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                # Draw frame number
                cv2.putText(vis_frame, f"Frame: {frame_number}/{total_frames}", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                # Encode frame as JPEG and store (only every Nth frame for preview optimization)
                # Always encode frame 0 to have immediate preview, then every Nth frame
                if frame_number == 0 or frame_number % preview_skip_frames == 0:
                    # Use lower quality JPEG for faster encoding
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
                    _, buffer = cv2.imencode('.jpg', vis_frame, encode_params)
                    tracking_frames[task_id] = buffer.tobytes()

                # Update progress
                frame_number += 1
                tracking_tasks[task_id].update({
                    "current_frame": frame_number,
                    "percentage": (frame_number / total_frames) * 100,
                })

        cap.release()
        cap = None

        # Thorough GPU memory cleanup
        if device == "cuda":
            # Delete model to free GPU memory
            if is_sam3:
                del predictor
                predictor = None
                sam3_generator = None
            else:
                del model
                model = None
            cleanup_gpu_memory(force=True)
            gc.collect()

            mem_info = get_gpu_memory_info()
            print(f"GPU Memory after cleanup: {mem_info['used']:.2f}GB used ({mem_info['utilization']:.1f}%)")

        # Save results
        results = {
            "video_name": request.video_filename,
            "experiment_type": request.rois.preset_name,
            "timestamp": datetime.now().isoformat(),
            "video_info": {
                "total_frames": total_frames,
                "fps": fps,
                "frame_width": frame_width,
                "frame_height": frame_height,
                "duration_sec": total_frames / fps if fps > 0 else 0,
            },
            "statistics": {
                "frames_without_detection": no_detection_count,
                "yolo_detections": yolo_detections,
                "template_detections": template_detections,
                "detection_rate": ((yolo_detections + template_detections) / total_frames * 100) if total_frames > 0 else 0,
            },
            "rois": [roi.model_dump() for roi in request.rois.rois],
            "tracking_data": tracking_data,
        }

        # Add ffprobe info if available
        if video_info:
            results["video_info"]["codec"] = video_info.get("codec", "unknown")
            results["video_info"]["ffprobe_duration"] = video_info.get("duration", 0)

        results_path = os.path.join(TRACKING_DIR, f"{task_id}_results.json")
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)

        tracking_tasks[task_id].update({
            "status": "completed",
            "results_path": results_path,
        })

        print(f"Tracking completed: {yolo_detections} YOLO, {template_detections} template, {no_detection_count} no detection")

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"Tracking error: {e}")
        print(f"Full traceback: {error_traceback}")
        tracking_tasks[task_id].update({
            "status": "error",
            "error": str(e),
        })
    finally:
        # Always cleanup resources to prevent memory leaks
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass

        try:
            if model is not None:
                del model
        except Exception:
            pass

        try:
            if 'predictor' in locals() and predictor is not None:
                del predictor
        except Exception:
            pass

        # Final GPU cleanup
        if torch.cuda.is_available():
            try:
                cleanup_gpu_memory(force=True)
                gc.collect()
                print("Final GPU memory cleanup completed")
            except Exception as cleanup_error:
                print(f"Error during final cleanup: {cleanup_error}")


@router.post("/start")
async def start_tracking(request: TrackingRequest, background_tasks: BackgroundTasks):
    """Start tracking process"""
    try:
        os.makedirs(TRACKING_DIR, exist_ok=True)

        # Generate task ID
        task_id = str(uuid.uuid4())

        # Start background task
        background_tasks.add_task(run_tracking_task, task_id, request)

        return ApiResponse(success=True, data={"task_id": task_id})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """Get tracking progress"""
    if task_id not in tracking_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tracking_tasks[task_id]

    return ApiResponse(
        success=True,
        data=ProcessingProgress(
            current_frame=task.get("current_frame", 0),
            total_frames=task.get("total_frames", 0),
            percentage=task.get("percentage", 0),
            status=task.get("status", "processing"),
            device=task.get("device"),
            error=task.get("error")
        ).model_dump()
    )


@router.post("/stop/{task_id}")
async def stop_tracking(task_id: str):
    """Stop tracking process"""
    if task_id not in tracking_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    tracking_tasks[task_id]["stopped"] = True
    tracking_tasks[task_id]["status"] = "stopped"

    return ApiResponse(success=True, data={"message": "Tracking stopped"})


def run_test_detection_task(task_id: str, request: TrackingRequest):
    """Background task to run single frame detection test"""
    predictor = None
    cap = None
    inference_state = None

    try:
        # Detect GPU availability
        if torch.cuda.is_available():
            device = "cuda"
            cleanup_gpu_memory(force=True)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        tracking_tasks[task_id] = {
            "status": "processing",
            "device": device,
            "percentage": 10,
        }

        video_path = os.path.join("temp/videos", request.video_filename)
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {request.video_filename}")

        tracking_tasks[task_id]["percentage"] = 20

        if 'sam' in request.model_name.lower() and SAM3_AVAILABLE:
            # Use SAM3 Reference Implementation
            model_path = os.path.join(MODEL_DIR, request.model_name)
            if not os.path.exists(model_path) and request.model_name.lower() == 'sam3':
                model_path = os.path.join(MODEL_DIR, "sam3.pt")

            tracking_tasks[task_id]["percentage"] = 30

            # Build model
            predictor = build_sam3_video_model(
                checkpoint_path=model_path,
                device=device,
                load_from_HF=False
            )

            tracking_tasks[task_id]["percentage"] = 40

            # Read ONLY the requested frame as PIL Image (to avoid loading entire video)
            cap = cv2.VideoCapture(video_path)
            frame_idx = request.frame_number if request.frame_number else 0
            if frame_idx > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            cap.release()
            cap = None

            if not ret:
                raise RuntimeError("Failed to read frame from video")

            # Convert frame to PIL Image
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_frame = Image.fromarray(frame_rgb)

            tracking_tasks[task_id]["percentage"] = 50

            # Initialize state with SINGLE FRAME (not entire video!) to save memory
            print(f"Initializing SAM3 state for single frame...")
            inference_state = predictor.init_state(
                resource_path=[pil_frame],  # Pass frame as list of PIL Images
                offload_video_to_cpu=True,  # Keep video frames on CPU to save GPU memory
            )

            tracking_tasks[task_id]["percentage"] = 70

            # Add text prompt at frame 0 (since we only have 1 frame)
            prompt = request.sam_prompt if request.sam_prompt else "mouse"
            print(f"SAM3 Test: Using prompt '{prompt}'")

            # add_prompt returns (frame_idx, out)
            _, out = predictor.add_prompt(
                inference_state,
                frame_idx=0,  # Always 0 since we only have 1 frame
                text_str=prompt,
                obj_id=1
            )

            tracking_tasks[task_id]["percentage"] = 80

            # Debug: Check what we got from SAM3
            print(f"SAM3 Test: Output keys: {out.keys() if out else 'None'}")
            if out and "obj_id_to_mask" in out:
                print(f"SAM3 Test: Found {len(out['obj_id_to_mask'])} objects")
            else:
                print("SAM3 Test: No obj_id_to_mask in output!")

            # Check alternative output formats
            if out:
                if "out_obj_ids" in out:
                    print(f"SAM3 Test: out_obj_ids = {out['out_obj_ids']}")
                if "out_binary_masks" in out:
                    print(f"SAM3 Test: Found {len(out['out_binary_masks'])} binary masks")

            # Use the same frame for visualization
            vis_frame = frame.copy()

            # Try different output formats from SAM3
            masks_found = False

            # Format 1: obj_id_to_mask (used in old test code)
            if out and "obj_id_to_mask" in out:
                print("SAM3 Test: Using obj_id_to_mask format")
                for obj_id, mask in out["obj_id_to_mask"].items():
                    # Convert boolean mask to uint8
                    mask_np = mask.cpu().numpy().astype(np.uint8) * 255
                    if len(mask_np.shape) == 3:
                        mask_np = mask_np[0]

                    # Find contours for drawing
                    contours, _ = cv2.findContours(mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        masks_found = True
                        # Draw segmentation mask with transparency
                        overlay = vis_frame.copy()
                        cv2.fillPoly(overlay, contours, (0, 255, 255))
                        cv2.addWeighted(overlay, 0.4, vis_frame, 0.6, 0, vis_frame)
                        cv2.polylines(vis_frame, contours, True, (0, 255, 255), 2)
                        print(f"SAM3 Test: Drew mask for object {obj_id}")

            # Format 2: out_binary_masks (used in tracking code)
            elif out and "out_binary_masks" in out and len(out["out_binary_masks"]) > 0:
                print("SAM3 Test: Using out_binary_masks format")
                for idx, mask in enumerate(out["out_binary_masks"]):
                    if torch.is_tensor(mask):
                        mask_np = mask.cpu().numpy().astype(np.uint8) * 255
                    else:
                        mask_np = np.array(mask).astype(np.uint8) * 255

                    if len(mask_np.shape) == 3:
                        mask_np = mask_np[0]

                    # Find contours for drawing
                    contours, _ = cv2.findContours(mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        masks_found = True
                        # Draw segmentation mask with transparency
                        overlay = vis_frame.copy()
                        cv2.fillPoly(overlay, contours, (0, 255, 255))
                        cv2.addWeighted(overlay, 0.4, vis_frame, 0.6, 0, vis_frame)
                        cv2.polylines(vis_frame, contours, True, (0, 255, 255), 2)
                        print(f"SAM3 Test: Drew mask {idx}")

            if not masks_found:
                print("SAM3 Test: No masks were drawn! Adding warning text to frame.")
                cv2.putText(vis_frame, "No objects detected", (50, 50),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

            tracking_tasks[task_id]["percentage"] = 90

            # Encode and store the result frame BEFORE cleanup
            _, buffer = cv2.imencode('.jpg', vis_frame)
            tracking_frames[task_id] = buffer.tobytes()

            # NOW cleanup SAM3 state/memory THOROUGHLY
            if inference_state is not None:
                # Clear internal caches similar to working implementation
                if "cached_features" in inference_state:
                    inference_state["cached_features"].clear()
                if "output_dict" in inference_state:
                    if "cond_frame_outputs" in inference_state["output_dict"]:
                        inference_state["output_dict"]["cond_frame_outputs"].clear()
                    if "non_cond_frame_outputs" in inference_state["output_dict"]:
                        inference_state["output_dict"]["non_cond_frame_outputs"].clear()
                if "input_batch" in inference_state:
                    del inference_state["input_batch"]
                inference_state.clear()
                del inference_state
                inference_state = None

            del predictor
            predictor = None
            if device == "cuda":
                torch.cuda.synchronize()
                cleanup_gpu_memory(force=True)
            gc.collect()

            # Mark as completed
            tracking_tasks[task_id].update({
                "status": "completed",
                "percentage": 100,
            })

        else:
            # Fallback to YOLO if not SAM or SAM3 not available
            model_path = os.path.join(MODEL_DIR, request.model_name)
            if not os.path.exists(model_path):
                # Check for sam3.pt if named sam3
                if request.model_name == 'sam3':
                    model_path = os.path.join(MODEL_DIR, 'sam3.pt')

                if not os.path.exists(model_path):
                    raise FileNotFoundError(f"Model not found: {request.model_name}")

            tracking_tasks[task_id]["percentage"] = 50

            cap = cv2.VideoCapture(video_path)
            if request.frame_number and request.frame_number > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, request.frame_number)
            ret, frame = cap.read()
            cap.release()
            cap = None

            vis_frame = frame.copy()
            model = YOLO(model_path)
            model.to(device)

            tracking_tasks[task_id]["percentage"] = 70

            results = model(frame, conf=request.confidence_threshold, device=device, verbose=False)

            if results and len(results) > 0:
                for box in results[0].boxes:
                    b = box.xyxy[0].cpu().numpy()
                    cv2.rectangle(vis_frame, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 255, 0), 2)

            tracking_tasks[task_id]["percentage"] = 90

            # Encode and store the result frame
            _, buffer = cv2.imencode('.jpg', vis_frame)
            tracking_frames[task_id] = buffer.tobytes()

            tracking_tasks[task_id].update({
                "status": "completed",
                "percentage": 100,
            })

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"Test detection error: {e}")
        print(f"Full traceback: {error_traceback}")
        tracking_tasks[task_id].update({
            "status": "error",
            "error": str(e),
        })
    finally:
        # Cleanup resources thoroughly
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass

        try:
            # Clean inference state first
            if inference_state is not None:
                if "cached_features" in inference_state:
                    inference_state["cached_features"].clear()
                if "output_dict" in inference_state:
                    if "cond_frame_outputs" in inference_state["output_dict"]:
                        inference_state["output_dict"]["cond_frame_outputs"].clear()
                    if "non_cond_frame_outputs" in inference_state["output_dict"]:
                        inference_state["output_dict"]["non_cond_frame_outputs"].clear()
                if "input_batch" in inference_state:
                    del inference_state["input_batch"]
                inference_state.clear()
                del inference_state
        except Exception:
            pass

        try:
            if predictor is not None:
                del predictor
        except Exception:
            pass

        # GPU cleanup
        if torch.cuda.is_available():
            try:
                torch.cuda.synchronize()
                cleanup_gpu_memory(force=True)
                gc.collect()
            except Exception as cleanup_error:
                print(f"Error during cleanup: {cleanup_error}")


@router.post("/test-detection")
async def test_detection(request: TrackingRequest, background_tasks: BackgroundTasks):
    """Run a single frame detection test (especially for SAM3) - now async to prevent blocking"""
    try:
        # Generate a temporary task ID for the test result
        task_id = f"test_{str(uuid.uuid4())[:8]}"

        # Start background task
        background_tasks.add_task(run_test_detection_task, task_id, request)

        return ApiResponse(success=True, data={"task_id": task_id})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/results/batch/prepare")
async def prepare_batch_download(req: BatchDownloadPrepareRequest):
    """Register a batch download. Returns a one-shot download_id to be streamed via GET."""
    if not req.task_ids:
        raise HTTPException(status_code=400, detail="task_ids is empty")

    for tid in req.task_ids:
        task = tracking_tasks.get(tid)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task not found: {tid}")
        if task.get("status") != "completed":
            raise HTTPException(status_code=400, detail=f"Task not completed: {tid}")
        results_path = task.get("results_path")
        if not results_path or not os.path.exists(results_path):
            raise HTTPException(status_code=404, detail=f"Results missing for task: {tid}")

    now_ts = time.time()
    for did, entry in list(batch_download_requests.items()):
        if now_ts - entry.get("created_at", 0) > BATCH_DOWNLOAD_TTL_SEC:
            del batch_download_requests[did]

    download_id = str(uuid.uuid4())
    batch_download_requests[download_id] = {
        "task_ids": list(req.task_ids),
        "batch_info": req.batch_info or {},
        "created_at": now_ts,
    }
    return ApiResponse(success=True, data={"download_id": download_id})


@router.get("/results/batch/{download_id}")
async def download_batch(download_id: str):
    """Stream a combined JSON of multiple tracking results without loading them into memory."""
    entry = batch_download_requests.pop(download_id, None)
    if not entry:
        raise HTTPException(status_code=404, detail="Batch download not found or already consumed")

    task_ids: List[str] = entry["task_ids"]
    batch_info: Dict[str, Any] = entry["batch_info"]

    paths: List[str] = []
    for tid in task_ids:
        task = tracking_tasks.get(tid)
        if not task or not task.get("results_path") or not os.path.exists(task["results_path"]):
            raise HTTPException(status_code=404, detail=f"Results missing for task: {tid}")
        paths.append(task["results_path"])

    def stream_combined_json():
        yield b'{"batch_info":'
        yield json.dumps(batch_info, ensure_ascii=False).encode("utf-8")
        yield b',"results":['
        for i, path in enumerate(paths):
            if i > 0:
                yield b","
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        yield b"]}"

    filename = f"batch_track_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return StreamingResponse(
        stream_combined_json(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/results/{task_id}")
async def download_results(task_id: str):
    """Download tracking results"""
    if task_id not in tracking_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tracking_tasks[task_id]

    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Tracking not completed")

    results_path = task.get("results_path")
    if not results_path or not os.path.exists(results_path):
        raise HTTPException(status_code=404, detail="Results not found")

    return FileResponse(
        results_path,
        media_type="application/json",
        filename=f"tracking_results_{task_id}.json"
    )


@router.get("/frame/{task_id}")
async def get_tracking_frame(task_id: str):
    """Get current tracking frame with visualization"""
    # Check if task exists
    if task_id not in tracking_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    # If frame is not yet available, return a waiting placeholder
    if task_id not in tracking_frames:
        # Create a simple placeholder frame
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, "Waiting for first frame...",
                   (120, 240),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        _, buffer = cv2.imencode('.jpg', placeholder)
        return StreamingResponse(io.BytesIO(buffer.tobytes()), media_type="image/jpeg")

    frame_bytes = tracking_frames[task_id]
    return StreamingResponse(io.BytesIO(frame_bytes), media_type="image/jpeg")


# ROI Template Management Endpoints

@router.post("/roi-templates/save")
async def save_roi_template(preset: ROIPreset):
    """Save ROI configuration as a template"""
    try:
        os.makedirs(ROI_TEMPLATES_DIR, exist_ok=True)

        # Create filename from preset name (sanitize)
        safe_name = "".join(c for c in preset.preset_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        filename = f"{safe_name}.json"
        filepath = os.path.join(ROI_TEMPLATES_DIR, filename)

        # Save template
        template_data = {
            "preset_name": preset.preset_name,
            "description": preset.description,
            "timestamp": datetime.now().isoformat(),
            "frame_width": preset.frame_width,
            "frame_height": preset.frame_height,
            "rois": [roi.model_dump() for roi in preset.rois]
        }

        with open(filepath, "w") as f:
            json.dump(template_data, f, indent=2)

        return ApiResponse(
            success=True,
            data={
                "message": "Template saved successfully",
                "template_name": preset.preset_name,
                "filename": filename
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roi-templates/list")
async def list_roi_templates():
    """List all saved ROI templates"""
    try:
        if not os.path.exists(ROI_TEMPLATES_DIR):
            os.makedirs(ROI_TEMPLATES_DIR, exist_ok=True)
            return ApiResponse(success=True, data={"templates": []})

        templates = []
        for filename in os.listdir(ROI_TEMPLATES_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(ROI_TEMPLATES_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        template_data = json.load(f)
                        templates.append({
                            "filename": filename,
                            "preset_name": template_data.get("preset_name", "Unknown"),
                            "description": template_data.get("description", ""),
                            "timestamp": template_data.get("timestamp", ""),
                            "roi_count": len(template_data.get("rois", []))
                        })
                except Exception as e:
                    print(f"Error reading template {filename}: {e}")

        # Sort by timestamp (newest first)
        templates.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return ApiResponse(success=True, data={"templates": templates})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roi-templates/load/{filename}")
async def load_roi_template(filename: str):
    """Load a specific ROI template"""
    try:
        filepath = os.path.join(ROI_TEMPLATES_DIR, filename)

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Template not found")

        with open(filepath, 'r') as f:
            template_data = json.load(f)

        return ApiResponse(success=True, data=template_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/roi-templates/delete/{filename}")
async def delete_roi_template(filename: str):
    """Delete a ROI template"""
    try:
        filepath = os.path.join(ROI_TEMPLATES_DIR, filename)

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Template not found")

        os.remove(filepath)

        return ApiResponse(
            success=True,
            data={"message": "Template deleted successfully"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
