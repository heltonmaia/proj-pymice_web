"""Tracking API endpoints"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
import os
import shutil
import uuid
import json
import io
import cv2
import torch
import subprocess
from datetime import datetime
from ultralytics import YOLO

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
)

router = APIRouter()

MODEL_DIR = "temp/models"
TRACKING_DIR = "temp/tracking"
ROI_TEMPLATES_DIR = "temp/roi_templates"

# Store tracking tasks
tracking_tasks = {}

# Store current tracking frames for live preview
tracking_frames = {}


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
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True)

    models = [f for f in os.listdir(MODEL_DIR) if f.endswith('.pt')]

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


def run_tracking_task(task_id: str, request: TrackingRequest):
    """Background task to run YOLO tracking"""
    try:
        # Detect GPU availability
        if torch.cuda.is_available():
            device = "cuda"
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

        # Load YOLO model
        model_path = os.path.join(MODEL_DIR, request.model_name)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {request.model_name}")

        model = YOLO(model_path)
        if device == "cuda":
            model.to("cuda")
        elif device == "mps":
            model.to("mps")

        # Open video
        video_path = os.path.join("temp/videos", request.video_filename)
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {request.video_filename}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Failed to open video file")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # Get video info using ffprobe
        video_info = get_video_info_ffprobe(video_path)
        if video_info:
            fps = video_info['fps']  # Use ffprobe FPS if available (more accurate)
            print(f"Video info from ffprobe: {fps} fps, {video_info['duration']:.2f}s duration")

        tracking_tasks[task_id]["total_frames"] = total_frames

        # Calculate background
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

        while True:
            if tracking_tasks[task_id].get("stopped"):
                break

            ret, frame = cap.read()
            if not ret:
                break

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
            )

            # Add timestamp information to frame data
            frame_data["timestamp_sec"] = timestamp_sec

            tracking_data.append(frame_data)

            # Update counters
            if frame_data["detection_method"] == "yolo":
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

            # Encode frame as JPEG and store
            _, buffer = cv2.imencode('.jpg', vis_frame)
            tracking_frames[task_id] = buffer.tobytes()

            # Update progress
            frame_number += 1
            tracking_tasks[task_id].update({
                "current_frame": frame_number,
                "percentage": (frame_number / total_frames) * 100,
            })

        cap.release()

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
        print(f"Tracking error: {e}")
        tracking_tasks[task_id].update({
            "status": "error",
            "error": str(e),
        })


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
            device=task.get("device")
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
    if task_id not in tracking_frames:
        raise HTTPException(status_code=404, detail="No frame available for this task")

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
