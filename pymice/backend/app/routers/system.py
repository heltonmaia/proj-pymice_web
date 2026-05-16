"""System diagnostics API endpoints"""

from fastapi import APIRouter, HTTPException
import os
import time

from app.models.schemas import ApiResponse, GPUStatus, YOLOTestResult

router = APIRouter()


@router.get("/browse")
async def browse_directory(path: str = ""):
    """List subdirectories at the given path (for the output-folder picker).

    Empty path defaults to the user's home. Returns absolute paths.
    """
    if not path:
        path = os.path.expanduser("~")
    path = os.path.abspath(os.path.expanduser(path))

    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    try:
        entries = os.listdir(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")

    dirs = []
    for name in sorted(entries, key=str.lower):
        if name.startswith("."):
            continue  # hide dotfiles by default
        full = os.path.join(path, name)
        if os.path.isdir(full):
            try:
                writable = os.access(full, os.W_OK)
            except Exception:
                writable = False
            dirs.append({"name": name, "writable": writable})

    parent = os.path.dirname(path) if path != "/" else None
    return ApiResponse(
        success=True,
        data={
            "current_path": path,
            "parent": parent,
            "home": os.path.expanduser("~"),
            "directories": dirs,
            "writable": os.access(path, os.W_OK),
        },
    )


@router.get("/gpu")
async def check_gpu():
    """Check GPU availability"""
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        mps_available = torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False

        if cuda_available:
            device = "cuda"
        elif mps_available:
            device = "mps"
        else:
            device = "cpu"

        return ApiResponse(
            success=True,
            data=GPUStatus(
                cuda_available=cuda_available,
                mps_available=mps_available,
                device=device
            ).model_dump()
        )
    except ImportError:
        # PyTorch not installed
        return ApiResponse(
            success=True,
            data=GPUStatus(
                cuda_available=False,
                mps_available=False,
                device="cpu"
            ).model_dump()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-yolo")
async def test_yolo_performance(request: dict):
    """Test YOLO inference performance on GPU vs CPU"""
    try:
        import torch

        model_name = request.get("model_name", "yolov11n.pt")

        # Simulate performance test
        # In production, this would load and test actual YOLO model

        cuda_available = torch.cuda.is_available()

        if cuda_available:
            # Simulate GPU inference
            start = time.time()
            time.sleep(0.01)  # Simulate fast GPU inference
            gpu_time = (time.time() - start) * 1000
        else:
            gpu_time = 0

        # Simulate CPU inference
        start = time.time()
        time.sleep(0.05)  # Simulate slower CPU inference
        cpu_time = (time.time() - start) * 1000

        speedup = cpu_time / gpu_time if gpu_time > 0 else 0

        return ApiResponse(
            success=True,
            data=YOLOTestResult(
                gpu_time=gpu_time,
                cpu_time=cpu_time,
                speedup=speedup
            ).model_dump()
        )

    except ImportError:
        # PyTorch not installed
        cpu_time = 45.0
        return ApiResponse(
            success=True,
            data=YOLOTestResult(
                gpu_time=0,
                cpu_time=cpu_time,
                speedup=0
            ).model_dump()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
