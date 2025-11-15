"""FastAPI main application"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.routers import camera, video, tracking, roi, analysis, system

app = FastAPI(
    title="PyMiceTracking Web API",
    description="Backend API for Mouse Behavioral Analysis",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(camera.router, prefix="/api/camera", tags=["Camera"])
app.include_router(video.router, prefix="/api/video", tags=["Video"])
app.include_router(tracking.router, prefix="/api/tracking", tags=["Tracking"])
app.include_router(roi.router, prefix="/api/roi", tags=["ROI"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(system.router, prefix="/api/system", tags=["System"])

# Static files for temp directory
os.makedirs("temp/videos", exist_ok=True)
os.makedirs("temp/models", exist_ok=True)
os.makedirs("temp/tracking", exist_ok=True)
os.makedirs("temp/analysis", exist_ok=True)


@app.get("/")
async def root():
    return {
        "message": "PyMiceTracking Web API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
