"""ROI Preset API endpoints"""

from fastapi import APIRouter, HTTPException
import os
import json

from app.models.schemas import ApiResponse, ROIPreset

router = APIRouter()

PRESET_DIR = "temp/presets"


@router.get("/presets")
async def list_presets():
    """List all ROI presets"""
    if not os.path.exists(PRESET_DIR):
        os.makedirs(PRESET_DIR, exist_ok=True)
        return ApiResponse(success=True, data={"presets": []})

    presets = [f.replace('.json', '') for f in os.listdir(PRESET_DIR) if f.endswith('.json')]

    return ApiResponse(success=True, data={"presets": presets})


@router.get("/presets/{name}")
async def load_preset(name: str):
    """Load a specific ROI preset"""
    filepath = os.path.join(PRESET_DIR, f"{name}.json")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Preset not found")

    try:
        with open(filepath, 'r') as f:
            preset_data = json.load(f)

        return ApiResponse(success=True, data=preset_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presets")
async def save_preset(preset: ROIPreset):
    """Save a new ROI preset"""
    try:
        os.makedirs(PRESET_DIR, exist_ok=True)

        filepath = os.path.join(PRESET_DIR, f"{preset.preset_name}.json")

        with open(filepath, 'w') as f:
            json.dump(preset.model_dump(), f, indent=2)

        return ApiResponse(
            success=True,
            data={"message": f"Preset '{preset.preset_name}' saved successfully"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/presets/{name}")
async def delete_preset(name: str):
    """Delete a ROI preset"""
    filepath = os.path.join(PRESET_DIR, f"{name}.json")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Preset not found")

    try:
        os.remove(filepath)
        return ApiResponse(
            success=True,
            data={"message": f"Preset '{name}' deleted successfully"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
