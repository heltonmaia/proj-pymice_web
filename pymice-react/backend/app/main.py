"""FastAPI main application"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import shutil

from app.routers import camera, video, tracking, roi, analysis, system

app = FastAPI(
    title="PyMiceTracking Web API",
    description="Backend API for Mouse Behavioral Analysis",
    version="1.0.0",
)


def cleanup_temp_directories():
    """Clean all temporary directories on startup"""
    # Directories to clean (but models directory will preserve .pt files)
    temp_dirs = [
        "temp/videos",
        "temp/tracking",
        "temp/analysis",
        "temp/models",
        "temp/roi_templates",
    ]

    print("\n" + "="*70)
    print("🧹 Cleaning temp directories on startup...")
    print("="*70)

    total_files = 0
    total_dirs = 0
    total_space = 0

    for temp_dir in temp_dirs:
        if not os.path.exists(temp_dir):
            continue

        print(f"\n📁 Cleaning: {temp_dir}")

        try:
            items = os.listdir(temp_dir)

            for item in items:
                item_path = os.path.join(temp_dir, item)

                # NEVER delete .pt model files from temp/models
                if temp_dir == "temp/models" and item.endswith('.pt'):
                    print(f"   📌 Preserved model: {item}")
                    continue

                try:
                    if os.path.isfile(item_path):
                        size = os.path.getsize(item_path)
                        os.remove(item_path)
                        total_files += 1
                        total_space += size
                        print(f"   🗑️  Removed file: {item} ({size / (1024*1024):.2f} MB)")

                    elif os.path.isdir(item_path):
                        size = sum(f.stat().st_size for f in os.scandir(item_path) if f.is_file())
                        shutil.rmtree(item_path)
                        total_dirs += 1
                        total_space += size
                        print(f"   🗑️  Removed directory: {item}/ ({size / (1024*1024):.2f} MB)")

                except Exception as e:
                    print(f"   ⚠️  Could not remove {item}: {e}")

            if len(items) == 0:
                print(f"   ✨ Already clean")

        except Exception as e:
            print(f"   ⚠️  Error cleaning directory: {e}")

    print("\n" + "="*70)
    print("📊 CLEANUP SUMMARY")
    print("="*70)
    print(f"✅ Files removed: {total_files}")
    print(f"✅ Directories removed: {total_dirs}")
    print(f"💾 Space freed: {total_space / (1024*1024):.2f} MB")
    print("="*70 + "\n")


@app.on_event("startup")
async def startup_event():
    """Run cleanup and setup on application startup"""
    # Clean temp directories
    cleanup_temp_directories()

    # Create temp directories if they don't exist
    os.makedirs("temp/videos", exist_ok=True)
    os.makedirs("temp/models", exist_ok=True)
    os.makedirs("temp/tracking", exist_ok=True)
    os.makedirs("temp/analysis", exist_ok=True)
    os.makedirs("temp/roi_templates", exist_ok=True)


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
