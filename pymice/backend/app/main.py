"""FastAPI main application"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import shutil

# Hide an unsupported GPU before any model code runs, so SAM3/Ultralytics/our own
# device picks all fall back to CPU instead of crashing on an arch this PyTorch
# build can't target (e.g. RTX 5060 Ti sm_120). No-op when the GPU is usable/absent.
from app.utils.device import disable_cuda_if_unsupported

if disable_cuda_if_unsupported():
    print("[startup] GPU arch unsupported by this PyTorch build — hiding CUDA; running on CPU.")

from app.routers import camera, video, tracking, roi, analysis, system, experiment

app = FastAPI(
    title="PyMice Web API",
    description="Backend API for Mouse Behavioral Analysis",
    version="1.0.0",
)


import time

def cleanup_temp_directories(max_age_seconds: int = 3600):
    """Clean temporary directories, but only for files older than max_age_seconds"""
    # NOTE: temp/experiments/ and temp/integrations.json are deliberately NOT cleaned —
    # they hold user data (recordings, hardware bindings) that must survive restarts.
    temp_dirs = [
        "temp/videos",
        "temp/tracking",
        "temp/analysis",
        # "temp/models",
        "temp/roi_templates",
    ]

    print("\n" + "="*70)
    print(f"🧹 Cleaning temp directories (older than {max_age_seconds/60:.0f} min)...")
    print("="*70)

    total_files = 0
    total_dirs = 0
    total_space = 0
    now = time.time()

    for temp_dir in temp_dirs:
        if not os.path.exists(temp_dir):
            continue

        print(f"\n📁 Checking: {temp_dir}")

        try:
            items = os.listdir(temp_dir)

            for item in items:
                item_path = os.path.join(temp_dir, item)

                # NEVER delete .pt model files from temp/models
                if temp_dir == "temp/models" and item.endswith('.pt'):
                    print(f"   📌 Preserved model: {item}")
                    continue

                # Check age
                try:
                    mtime = os.path.getmtime(item_path)
                    if now - mtime < max_age_seconds:
                        print(f"   ⏩ Skipping recent file: {item}")
                        continue
                except Exception:
                    pass

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


def _mark_orphan_experiments():
    """If a previous run died, any experiment still marked 'running' in
    metadata.json is now an orphan — flag it as crashed."""
    import json
    base = "temp/experiments"
    if not os.path.isdir(base):
        return
    for entry in os.listdir(base):
        meta_path = os.path.join(base, entry, "metadata.json")
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            if meta.get("state") == "running":
                meta["state"] = "crashed"
                with open(meta_path, "w") as f:
                    json.dump(meta, f, indent=2)
                print(f"⚠️  Marked orphan experiment as crashed: {entry}")
        except Exception as e:
            print(f"   Could not check {entry}: {e}")


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
    os.makedirs("temp/experiments", exist_ok=True)
    _mark_orphan_experiments()

    # Idle-camera watchdog: releases the cap if no /frame request has been
    # seen for ~30s — catches "user closed the tab" without us ever knowing,
    # so the camera LED stops staying on.
    from app.routers.camera import start_watchdog
    start_watchdog()


@app.on_event("shutdown")
async def shutdown_event():
    """Release shared resources cleanly on SIGTERM/SIGINT.

    Order matters: experiment first (its loop reads the camera), then the
    camera itself, then the watchdog.
    """
    print("\n🧹 Shutdown: stopping experiment and releasing camera...")
    try:
        from app.routers.experiment import abort_running_experiment
        abort_running_experiment(reason="backend_shutdown")
    except Exception as e:
        print(f"   ⚠ abort_running_experiment raised: {e}")
    try:
        from app.routers.camera import release_camera, stop_watchdog
        release_camera(reason="backend_shutdown")
        stop_watchdog()
    except Exception as e:
        print(f"   ⚠ camera release raised: {e}")
    print("✅ Shutdown complete.")


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5765"],
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
app.include_router(experiment.router, prefix="/api/experiment", tags=["Experiment"])


@app.get("/")
async def root():
    return {
        "message": "PyMice Web API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
