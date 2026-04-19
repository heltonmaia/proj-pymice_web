"""Camera API endpoints"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import cv2
import io
from typing import Optional

from app.models.schemas import ApiResponse, StreamRequest, RecordingRequest

router = APIRouter()

# Global camera state
camera_state = {
    "stream": None,
    "recording": None,
    "device_id": None,
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

        camera_state["stream"] = cap
        camera_state["device_id"] = request.device_id

        return ApiResponse(
            success=True,
            data={"message": f"Stream started on device {request.device_id}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream/stop")
async def stop_stream():
    """Stop camera stream"""
    if camera_state["stream"]:
        camera_state["stream"].release()
        camera_state["stream"] = None

    return ApiResponse(success=True, data={"message": "Stream stopped"})


@router.get("/frame")
async def get_frame():
    """Get current frame from camera stream"""
    if not camera_state["stream"]:
        raise HTTPException(status_code=400, detail="No active stream")

    ret, frame = camera_state["stream"].read()
    if not ret:
        raise HTTPException(status_code=500, detail="Failed to read frame")

    # Se está gravando, escrever o frame no vídeo
    if camera_state["recording"] and camera_state["recording"]["writer"]:
        camera_state["recording"]["writer"].write(frame)

    # Encode frame as JPEG
    _, buffer = cv2.imencode('.jpg', frame)
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
