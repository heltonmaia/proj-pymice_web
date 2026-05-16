"""Camera API endpoints"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import cv2
import io
import threading
from typing import Optional

from app.models.schemas import ApiResponse, StreamRequest, RecordingRequest, CameraPropertiesUpdate


JPEG_QUALITY = 75  # quality/size trade-off for the preview pipeline


def _apply_camera_settings(cap, width=None, height=None, brightness=None):
    """Apply optional resolution + brightness to an open VideoCapture.

    Brightness in 0–100 maps to the camera's native CAP_PROP_BRIGHTNESS scale —
    OpenCV normalises this to 0.0–1.0 on most V4L2 backends, so we send /100.
    Cameras that don't support a property silently ignore the set() call.
    """
    if width and height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    if brightness is not None:
        cap.set(cv2.CAP_PROP_BRIGHTNESS, max(0.0, min(1.0, brightness / 100.0)))
    # Minimum buffer to avoid stale frames piling up in the V4L2 queue (low latency).
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

router = APIRouter()

# Global camera state
camera_state = {
    "stream": None,
    "recording": None,
    "device_id": None,
    "annotated_frame": None,
    "annotated_lock": threading.Lock(),
}


@router.get("/devices")
async def list_devices():
    """List available camera devices"""
    devices = []
    for i in range(10):  # Check first 10 devices
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            devices.append(i)
            cap.release()
        else:
            break

    return ApiResponse(success=True, data={"devices": devices})


@router.post("/stream/start")
async def start_stream(request: StreamRequest):
    """Start camera stream"""
    try:
        cap = cv2.VideoCapture(request.device_id)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Failed to open camera")

        _apply_camera_settings(cap, request.width, request.height, request.brightness)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        camera_state["stream"] = cap
        camera_state["device_id"] = request.device_id

        return ApiResponse(
            success=True,
            data={
                "message": f"Stream started on device {request.device_id}",
                "width": actual_w,
                "height": actual_h,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/properties")
async def update_camera_properties(props: CameraPropertiesUpdate):
    """Update mutable camera properties (currently: brightness) on the live stream."""
    cap = camera_state.get("stream")
    if cap is None:
        raise HTTPException(status_code=400, detail="No active stream")
    _apply_camera_settings(cap, brightness=props.brightness)
    return ApiResponse(success=True, data={"applied": props.model_dump(exclude_none=True)})


@router.post("/stream/stop")
async def stop_stream():
    """Stop camera stream"""
    if camera_state["stream"]:
        camera_state["stream"].release()
        camera_state["stream"] = None
    with camera_state["annotated_lock"]:
        camera_state["annotated_frame"] = None

    return ApiResponse(success=True, data={"message": "Stream stopped"})


@router.get("/frame")
async def get_frame():
    """Get current frame from camera stream.

    If a LiveExperiment is running and has injected an annotated frame,
    we serve that instead of the raw capture so the UI shows overlays
    without a separate endpoint.
    """
    annotated = None
    with camera_state["annotated_lock"]:
        if camera_state["annotated_frame"] is not None:
            annotated = camera_state["annotated_frame"].copy()

    if annotated is not None:
        _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return StreamingResponse(io.BytesIO(buffer.tobytes()), media_type="image/jpeg")

    if not camera_state["stream"]:
        raise HTTPException(status_code=400, detail="No active stream")

    ret, frame = camera_state["stream"].read()
    if not ret:
        raise HTTPException(status_code=500, detail="Failed to read frame")

    if camera_state["recording"] and camera_state["recording"]["writer"]:
        camera_state["recording"]["writer"].write(frame)

    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return StreamingResponse(io.BytesIO(buffer.tobytes()), media_type="image/jpeg")


@router.post("/record/start")
async def start_recording(request: RecordingRequest):
    """Start recording video"""
    from datetime import datetime
    import os

    if not camera_state["stream"]:
        raise HTTPException(status_code=400, detail="No active stream")

    # Generate filename
    if not request.filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.mp4"
    else:
        filename = request.filename

    filepath = os.path.join("temp/videos", filename)

    # Get frame properties
    width = int(camera_state["stream"].get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(camera_state["stream"].get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = 30.0

    # Create video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    # Verificar se o writer foi criado com sucesso
    if not writer.isOpened():
        raise HTTPException(
            status_code=500,
            detail="Failed to create video writer. Check codec and file path."
        )

    camera_state["recording"] = {
        "writer": writer,
        "filename": filename,
        "filepath": filepath,
    }

    return ApiResponse(success=True, data={"filename": filename})


@router.post("/record/stop")
async def stop_recording():
    """Stop recording video"""
    if not camera_state["recording"]:
        raise HTTPException(status_code=400, detail="No active recording")

    camera_state["recording"]["writer"].release()
    filename = camera_state["recording"]["filename"]
    camera_state["recording"] = None

    return ApiResponse(success=True, data={"filename": filename})
