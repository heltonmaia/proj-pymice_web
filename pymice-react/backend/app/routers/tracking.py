"""Tracking API endpoints"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import os
import shutil
import uuid
import json
from datetime import datetime

from app.models.schemas import (
    ApiResponse,
    TrackingRequest,
    ProcessingProgress,
    UploadResponse
)

router = APIRouter()

MODEL_DIR = "temp/models"
TRACKING_DIR = "temp/tracking"

# Store tracking tasks
tracking_tasks = {}


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
    """Background task to run tracking"""
    try:
        tracking_tasks[task_id] = {
            "status": "processing",
            "current_frame": 0,
            "total_frames": 100,  # Will be updated
            "percentage": 0,
        }

        # Simulate tracking process
        # In production, this would call the actual YOLO tracking code
        import time
        total_frames = 100

        for frame in range(total_frames):
            if tracking_tasks[task_id].get("stopped"):
                break

            tracking_tasks[task_id].update({
                "current_frame": frame + 1,
                "total_frames": total_frames,
                "percentage": ((frame + 1) / total_frames) * 100,
            })

            time.sleep(0.1)  # Simulate processing time

        # Save results
        results = {
            "video_name": request.video_filename,
            "experiment_type": request.rois.preset_name,
            "timestamp": datetime.now().isoformat(),
            "total_frames": total_frames,
            "frames_without_detection": 5,
            "yolo_detections": 95,
            "template_detections": 0,
            "rois": [roi.model_dump() for roi in request.rois.rois],
            "tracking_data": [],
        }

        results_path = os.path.join(TRACKING_DIR, f"{task_id}_results.json")
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)

        tracking_tasks[task_id].update({
            "status": "completed",
            "results_path": results_path,
        })

    except Exception as e:
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
            status=task.get("status", "processing")
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
