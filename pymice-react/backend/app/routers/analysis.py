"""Analysis API endpoints"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

from app.models.schemas import (
    ApiResponse,
    HeatmapRequest,
    TrackingData,
    OpenFieldAnalysisRequest,
    VideoExportRequest
)

router = APIRouter()


@router.post("/heatmap")
async def generate_heatmap(request: HeatmapRequest):
    """Generate movement heatmap from tracking data"""
    try:
        tracking_data = request.tracking_data
        settings = request.settings

        # Extract centroids
        x_coords = [frame.centroid_x for frame in tracking_data.tracking_data]
        y_coords = [frame.centroid_y for frame in tracking_data.tracking_data]

        if not x_coords:
            raise HTTPException(status_code=400, detail="No tracking data available")

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 8))

        # Generate 2D histogram
        heatmap, xedges, yedges = np.histogram2d(
            x_coords,
            y_coords,
            bins=settings.resolution
        )

        # Plot heatmap
        extent = [0, tracking_data.rois[0].center_x * 2 if tracking_data.rois else 640,
                 0, tracking_data.rois[0].center_y * 2 if tracking_data.rois else 480]

        im = ax.imshow(
            heatmap.T,
            origin='lower',
            extent=extent,
            cmap=settings.colormap,
            alpha=settings.transparency
        )

        plt.colorbar(im, ax=ax, label='Density')
        ax.set_xlabel('X Position')
        ax.set_ylabel('Y Position')
        ax.set_title('Movement Heatmap')

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()

        return StreamingResponse(buf, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/movement")
async def analyze_movement(tracking_data: TrackingData):
    """Analyze movement patterns"""
    try:
        # Calculate basic statistics
        x_coords = [frame.centroid_x for frame in tracking_data.tracking_data]
        y_coords = [frame.centroid_y for frame in tracking_data.tracking_data]

        # Calculate velocities
        velocities = []
        for i in range(1, len(x_coords)):
            dx = x_coords[i] - x_coords[i-1]
            dy = y_coords[i] - y_coords[i-1]
            velocity = np.sqrt(dx**2 + dy**2)
            velocities.append(velocity)

        results = {
            "total_distance": sum(velocities),
            "average_velocity": np.mean(velocities) if velocities else 0,
            "max_velocity": np.max(velocities) if velocities else 0,
            "center_of_mass": {
                "x": np.mean(x_coords),
                "y": np.mean(y_coords)
            },
            "frames_analyzed": len(tracking_data.tracking_data),
        }

        return ApiResponse(success=True, data=results)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/open-field")
async def analyze_open_field(request: OpenFieldAnalysisRequest):
    """Analyze open field test data"""
    try:
        tracking_data = request.tracking_data

        # Calculate distance from center
        center_time = 0
        periphery_time = 0

        for frame in tracking_data.tracking_data:
            dx = frame.centroid_x - request.arena_center_x
            dy = frame.centroid_y - request.arena_center_y
            distance = np.sqrt(dx**2 + dy**2)

            # Consider center as inner 50% of radius
            if distance < request.arena_radius * 0.5:
                center_time += 1
            else:
                periphery_time += 1

        total_time = center_time + periphery_time

        results = {
            "center_time": center_time,
            "periphery_time": periphery_time,
            "center_percentage": (center_time / total_time * 100) if total_time > 0 else 0,
            "periphery_percentage": (periphery_time / total_time * 100) if total_time > 0 else 0,
            "total_frames": total_time,
        }

        return ApiResponse(success=True, data=results)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-video")
async def export_video(request: VideoExportRequest):
    """Export video with tracking overlay"""
    # This would require actual video processing
    # For now, return a placeholder response
    raise HTTPException(status_code=501, detail="Video export not yet implemented")
