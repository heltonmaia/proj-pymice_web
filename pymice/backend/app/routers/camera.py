"""Camera API endpoints + global camera lifecycle.

The cv2.VideoCapture instance held in `camera_state["stream"]` is shared by
two consumers:
  - the /camera/frame preview poll (browser display)
  - the LiveExperiment loop (recording / detection)

To ensure the camera is always released — even when the browser crashes,
the user reloads the tab, or the backend is killed — we maintain:
  - `release_camera()`: idempotent helper that stops the running experiment
    (if any) and releases the cap. Called from /stream/stop, from the idle
    watchdog, and from the FastAPI shutdown event.
  - `_last_frame_request_at`: timestamp updated on every /frame fetch; if
    nothing is consuming frames for IDLE_RELEASE_SECONDS and no experiment
    is running, the watchdog calls release_camera() — this catches the
    closed-tab scenario.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import cv2
import io
import threading

from app.models.schemas import ApiResponse, StreamRequest, RecordingRequest, CameraPropertiesUpdate

logger = logging.getLogger("pymice.camera")

IDLE_RELEASE_SECONDS = 30.0
WATCHDOG_INTERVAL_SECONDS = 5.0


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
    "last_frame_request_at": 0.0,  # monotonic; updated on every /frame fetch
}

# Module-level lifecycle primitives.
_camera_lock = threading.Lock()  # serialises open/release across threads
_watchdog_stop = threading.Event()
_watchdog_thread: Optional[threading.Thread] = None


def release_camera(reason: str = "user") -> bool:
    """Release the camera and clear annotated state. Idempotent.

    Aborts a running experiment first (releasing while the loop is reading
    would crash it). Returns True if the cap was actually released.
    """
    # Late import to avoid cyclic dependency between camera and experiment routers.
    try:
        from app.routers.experiment import abort_running_experiment
        abort_running_experiment(reason=f"camera_released:{reason}")
    except Exception as e:
        logger.warning("could not abort running experiment during release: %s", e)

    released = False
    with _camera_lock:
        cap = camera_state.get("stream")
        if cap is not None:
            try:
                cap.release()
                released = True
                logger.info("camera released (reason=%s)", reason)
            except Exception as e:
                logger.exception("cap.release() raised: %s", e)
            camera_state["stream"] = None
        with camera_state["annotated_lock"]:
            camera_state["annotated_frame"] = None
    return released


def _watchdog_loop() -> None:
    """Release the camera if no consumer has touched it for IDLE_RELEASE_SECONDS.

    A consumer is either:
      - the /camera/frame preview poll (updates last_frame_request_at)
      - a running experiment (its loop reads cap directly)
    """
    # Late import for the same cyclic reason as release_camera.
    while not _watchdog_stop.wait(WATCHDOG_INTERVAL_SECONDS):
        try:
            if camera_state.get("stream") is None:
                continue

            try:
                from app.routers.experiment import is_experiment_running
                if is_experiment_running():
                    continue
            except Exception:
                pass

            last = camera_state.get("last_frame_request_at") or 0.0
            idle = time.monotonic() - last
            if idle >= IDLE_RELEASE_SECONDS:
                logger.info(
                    "idle watchdog: no frame consumer for %.1fs, releasing camera",
                    idle,
                )
                release_camera(reason="idle_watchdog")
        except Exception as e:
            logger.exception("watchdog iteration failed: %s", e)


def start_watchdog() -> None:
    global _watchdog_thread
    if _watchdog_thread is not None and _watchdog_thread.is_alive():
        return
    _watchdog_stop.clear()
    _watchdog_thread = threading.Thread(target=_watchdog_loop, daemon=True, name="camera-watchdog")
    _watchdog_thread.start()
    logger.info("camera idle watchdog started (idle=%ss, tick=%ss)", IDLE_RELEASE_SECONDS, WATCHDOG_INTERVAL_SECONDS)


def stop_watchdog() -> None:
    _watchdog_stop.set()
    if _watchdog_thread is not None:
        _watchdog_thread.join(timeout=3.0)


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
        camera_state["last_frame_request_at"] = time.monotonic()  # grace period

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
    """Stop camera stream — also aborts a running experiment cleanly."""
    released = release_camera(reason="user_stop_stream")
    return ApiResponse(success=True, data={"message": "Stream stopped", "released": released})


@router.get("/health")
async def camera_health():
    """Diagnostic snapshot of the camera lifecycle. Useful when triaging LED-stays-on."""
    cap = camera_state.get("stream")
    info = {
        "open": cap is not None,
        "device_id": camera_state.get("device_id"),
        "has_annotated_frame": camera_state.get("annotated_frame") is not None,
        "last_frame_request_age_sec": (
            (time.monotonic() - camera_state["last_frame_request_at"])
            if camera_state.get("last_frame_request_at") else None
        ),
    }
    if cap is not None:
        try:
            info["actual_width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            info["actual_height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            info["actual_fps"] = float(cap.get(cv2.CAP_PROP_FPS))
        except Exception:
            pass
    return ApiResponse(success=True, data=info)


@router.get("/frame")
async def get_frame():
    """Get current frame from camera stream.

    If a LiveExperiment is running and has injected an annotated frame,
    we serve that instead of the raw capture so the UI shows overlays
    without a separate endpoint.
    """
    camera_state["last_frame_request_at"] = time.monotonic()
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
