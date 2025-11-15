"""Video management API endpoints"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os
import shutil
import cv2

from app.models.schemas import ApiResponse, VideoInfo, UploadResponse

router = APIRouter()

VIDEO_DIR = "temp/videos"


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file"""
    try:
        os.makedirs(VIDEO_DIR, exist_ok=True)
        filepath = os.path.join(VIDEO_DIR, file.filename)

        # Save uploaded file
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


@router.get("/info/{filename}")
async def get_video_info(filename: str):
    """Get video file information"""
    filepath = os.path.join(VIDEO_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        cap = cv2.VideoCapture(filepath)

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        cap.release()

        return ApiResponse(
            success=True,
            data=VideoInfo(
                filename=filename,
                width=width,
                height=height,
                fps=fps,
                total_frames=total_frames,
                duration=duration
            ).model_dump()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
async def download_video(filename: str):
    """Download a video file"""
    filepath = os.path.join(VIDEO_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(filepath, media_type="video/mp4", filename=filename)


@router.get("/list")
async def list_videos():
    """List all uploaded videos"""
    if not os.path.exists(VIDEO_DIR):
        return ApiResponse(success=True, data={"videos": []})

    videos = [f for f in os.listdir(VIDEO_DIR) if f.endswith(('.mp4', '.avi', '.mov'))]

    return ApiResponse(success=True, data={"videos": videos})
