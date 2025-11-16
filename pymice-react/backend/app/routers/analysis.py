"""Analysis API endpoints"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import scipy.ndimage as ndimage
import io
import json
import zipfile
import tempfile
import os
from pathlib import Path
from datetime import datetime

from app.models.schemas import (
    ApiResponse,
    HeatmapRequest,
    TrackingData,
    OpenFieldAnalysisRequest,
    VideoExportRequest
)

router = APIRouter()
TEMP_DIR = Path("temp/analysis")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/heatmap")
async def generate_heatmap(request: HeatmapRequest):
    """Generate movement heatmap from tracking data"""
    try:
        tracking_data = request.tracking_data
        settings = request.settings

        # Extract centroids (skip None values)
        x_coords = []
        y_coords = []
        for frame in tracking_data.tracking_data:
            if frame.centroid_x is not None and frame.centroid_y is not None:
                x_coords.append(frame.centroid_x)
                y_coords.append(frame.centroid_y)

        if not x_coords:
            raise HTTPException(status_code=400, detail="No tracking data available")

        x_coords = np.array(x_coords)
        y_coords = np.array(y_coords)

        # Calculate center of mass
        center_x = np.mean(x_coords)
        center_y = np.mean(y_coords)

        # Create figure with higher quality
        fig, ax = plt.subplots(figsize=(12, 8))

        # Generate 2D histogram with density normalization
        heatmap, xedges, yedges = np.histogram2d(
            x_coords,
            y_coords,
            bins=settings.resolution,
            density=True  # Normalize to density
        )

        # Apply Gaussian smoothing for better visualization
        heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=settings.gaussian_sigma)

        # Calculate proper extent from actual data
        extent = [
            min(x_coords),
            max(x_coords),
            min(y_coords),
            max(y_coords)
        ]

        # Plot smoothed heatmap
        im = ax.imshow(
            heatmap_smooth.T,
            origin='lower',
            extent=extent,
            cmap=settings.colormap,
            aspect='equal',  # Maintain aspect ratio
            alpha=settings.transparency,
            interpolation='bilinear'  # Smooth interpolation
        )

        # Plot trajectory overlay
        ax.plot(x_coords, y_coords, 'k-', alpha=0.3, linewidth=0.5, label='Trajectory')

        # Mark center of mass
        ax.scatter(center_x, center_y, c='red', s=100, marker='x',
                  linewidth=3, label='Center of Mass', zorder=5)

        # Add colorbar and labels
        plt.colorbar(im, ax=ax, label='Movement Density', shrink=0.8)
        ax.set_xlabel('X Position (pixels)', fontsize=12)
        ax.set_ylabel('Y Position (pixels)', fontsize=12)
        ax.set_title('Animal Movement Heatmap', fontsize=16, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend()

        # Save to buffer with high DPI
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()

        return StreamingResponse(buf, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/movement")
async def analyze_movement(tracking_data: TrackingData):
    """Analyze movement patterns and generate velocity plots"""
    try:
        # Extract data (skip None values)
        frames = []
        x_coords = []
        y_coords = []
        timestamps = []

        for frame in tracking_data.tracking_data:
            if frame.centroid_x is not None and frame.centroid_y is not None:
                frames.append(frame.frame_number)
                x_coords.append(frame.centroid_x)
                y_coords.append(frame.centroid_y)
                timestamps.append(frame.timestamp_sec)

        if len(frames) < 2:
            raise HTTPException(status_code=400, detail="Not enough tracking data")

        x_coords = np.array(x_coords)
        y_coords = np.array(y_coords)
        timestamps = np.array(timestamps)

        # Calculate velocities using timestamps (pixels/second)
        velocities = []
        for i in range(1, len(x_coords)):
            dx = x_coords[i] - x_coords[i-1]
            dy = y_coords[i] - y_coords[i-1]
            dt = timestamps[i] - timestamps[i-1]

            if dt > 0:
                distance = np.sqrt(dx**2 + dy**2)
                velocity = distance / dt  # pixels/second
                velocities.append(velocity)
            else:
                velocities.append(0)

        velocities = np.array(velocities)

        # Calculate statistics
        total_distance = np.sum([np.sqrt((x_coords[i] - x_coords[i-1])**2 +
                                         (y_coords[i] - y_coords[i-1])**2)
                                 for i in range(1, len(x_coords))])

        movement_threshold = np.percentile(velocities, settings.movement_threshold_percentile) if len(velocities) > 0 else 0
        moving_frames = velocities > movement_threshold
        stationary_ratio = 1 - (np.sum(moving_frames) / len(moving_frames)) if len(moving_frames) > 0 else 1

        # Create figure with movement analysis
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

        # Plot 1: Velocity over time
        ax1 = fig.add_subplot(gs[0, :])
        time_points = timestamps[1:]  # Skip first frame
        ax1.plot(time_points, velocities, 'g-', linewidth=1, alpha=0.7, label='Velocity')
        ax1.axhline(y=np.mean(velocities), color='r', linestyle='--',
                   label=f'Mean: {np.mean(velocities):.1f} px/s')
        ax1.axhline(y=movement_threshold, color='orange', linestyle=':',
                   label=f'Movement threshold: {movement_threshold:.1f} px/s')
        ax1.set_title('Movement Velocity Over Time', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Time (seconds)', fontsize=12)
        ax1.set_ylabel('Velocity (pixels/second)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # Plot 2: Velocity distribution
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.hist(velocities, bins=settings.velocity_bins, alpha=0.7, color='purple', edgecolor='black')
        ax2.axvline(x=np.mean(velocities), color='r', linestyle='--',
                   label=f'Mean: {np.mean(velocities):.1f} px/s')
        ax2.axvline(x=movement_threshold, color='orange', linestyle=':',
                   label='Movement threshold')
        ax2.set_title('Velocity Distribution', fontsize=13, fontweight='bold')
        ax2.set_xlabel('Velocity (pixels/second)', fontsize=12)
        ax2.set_ylabel('Frequency', fontsize=12)
        ax2.legend()

        # Plot 3: Activity classification
        ax3 = fig.add_subplot(gs[1, 1])
        labels = ['Moving', 'Stationary']
        sizes = [1 - stationary_ratio, stationary_ratio]
        colors = ['#ff9999', '#66b3ff']
        ax3.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
        ax3.set_title('Activity Classification', fontsize=13, fontweight='bold')

        # Add statistics text
        stats_text = (
            f"Total Distance: {total_distance:.1f} px\n"
            f"Duration: {timestamps[-1] - timestamps[0]:.2f} s\n"
            f"Mean Velocity: {np.mean(velocities):.2f} px/s\n"
            f"Max Velocity: {np.max(velocities):.2f} px/s\n"
            f"Min Velocity: {np.min(velocities):.2f} px/s\n"
            f"Stationary Time: {stationary_ratio*100:.1f}%\n"
            f"Moving Time: {(1-stationary_ratio)*100:.1f}%"
        )
        fig.text(0.02, 0.02, stats_text, fontsize=10, fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))

        plt.suptitle('Movement Analysis', fontsize=16, fontweight='bold', y=0.98)

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()

        return StreamingResponse(buf, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/complete")
async def generate_complete_analysis(request: HeatmapRequest):
    """Generate complete analysis panel with heatmap and movement analysis"""
    try:
        tracking_data = request.tracking_data
        settings = request.settings

        # Extract data (skip None values)
        frames = []
        x_coords = []
        y_coords = []
        timestamps = []

        for frame in tracking_data.tracking_data:
            if frame.centroid_x is not None and frame.centroid_y is not None:
                frames.append(frame.frame_number)
                x_coords.append(frame.centroid_x)
                y_coords.append(frame.centroid_y)
                timestamps.append(frame.timestamp_sec)

        if len(frames) < 2:
            raise HTTPException(status_code=400, detail="Not enough tracking data")

        x_coords = np.array(x_coords)
        y_coords = np.array(y_coords)
        timestamps = np.array(timestamps)

        # Calculate center of mass
        center_x = np.mean(x_coords)
        center_y = np.mean(y_coords)

        # Calculate velocities using timestamps
        velocities = []
        for i in range(1, len(x_coords)):
            dx = x_coords[i] - x_coords[i-1]
            dy = y_coords[i] - y_coords[i-1]
            dt = timestamps[i] - timestamps[i-1]
            if dt > 0:
                distance = np.sqrt(dx**2 + dy**2)
                velocity = distance / dt
                velocities.append(velocity)
            else:
                velocities.append(0)

        velocities = np.array(velocities)

        # Calculate statistics
        total_distance = np.sum([np.sqrt((x_coords[i] - x_coords[i-1])**2 +
                                         (y_coords[i] - y_coords[i-1])**2)
                                 for i in range(1, len(x_coords))])
        movement_threshold = np.percentile(velocities, settings.movement_threshold_percentile) if len(velocities) > 0 else 0
        moving_frames = velocities > movement_threshold
        stationary_ratio = 1 - (np.sum(moving_frames) / len(moving_frames)) if len(moving_frames) > 0 else 1
        distances_from_center = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2)

        # Create complete analysis panel
        fig = plt.figure(figsize=(24, 14))
        gs = fig.add_gridspec(2, 3, height_ratios=[2.5, 1.2], width_ratios=[1.5, 1, 1.5],
                             hspace=0.3, wspace=0.25)

        # Plot 1: High-resolution Movement Heatmap
        ax1 = fig.add_subplot(gs[0, :2])
        heatmap, _, _ = np.histogram2d(x_coords, y_coords, bins=settings.resolution, density=True)
        heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=settings.gaussian_sigma)

        extent = [min(x_coords), max(x_coords), min(y_coords), max(y_coords)]
        im = ax1.imshow(
            heatmap_smooth.T,
            origin='lower',
            extent=extent,
            cmap=settings.colormap,
            aspect='equal',
            alpha=settings.transparency,
            interpolation='bilinear'
        )

        ax1.plot(x_coords, y_coords, 'k-', alpha=0.3, linewidth=0.5, label='Trajectory')
        ax1.scatter(center_x, center_y, c='red', s=100, marker='x',
                   linewidth=3, label='Center of Mass')

        plt.colorbar(im, ax=ax1, label='Movement Density', shrink=0.6)
        ax1.set_title('Animal Movement Heatmap', fontsize=16, fontweight='bold')
        ax1.set_xlabel('X Position (pixels)', fontsize=12)
        ax1.set_ylabel('Y Position (pixels)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # Plot 2: Statistics Summary
        ax2 = fig.add_subplot(gs[0, 2])
        ax2.axis('off')
        ax2.set_title('Analysis Summary', fontsize=16, fontweight='bold', pad=20, y=1.0)

        stats_text = (
            f"Total Frames: {len(frames)}\n"
            f"Duration: {timestamps[-1] - timestamps[0]:.2f}s\n"
            f"\n"
            f"Spatial Statistics:\n"
            f"  Center: ({center_x:.0f}, {center_y:.0f})\n"
            f"  Mean dist: {np.mean(distances_from_center):.1f}px\n"
            f"  Max dist: {np.max(distances_from_center):.1f}px\n"
            f"\n"
            f"Movement Statistics:\n"
            f"  Total dist: {total_distance:.1f}px\n"
            f"  Mean vel: {np.mean(velocities):.2f}px/s\n"
            f"  Max vel: {np.max(velocities):.2f}px/s\n"
            f"  Threshold: {movement_threshold:.2f}px/s\n"
            f"  Stationary: {stationary_ratio*100:.1f}%\n"
            f"  Moving: {(1-stationary_ratio)*100:.1f}%\n"
            f"\n"
            f"Configuration:\n"
            f"  Bins: {settings.resolution}\n"
            f"  Colormap: {settings.colormap}\n"
            f"  Alpha: {settings.transparency}"
        )

        ax2.text(0.08, 0.88, stats_text, transform=ax2.transAxes,
                fontsize=13, verticalalignment='top', fontfamily='sans-serif',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.95, pad=1.2),
                linespacing=1.5, weight='normal')

        # Plot 3: Movement velocity over time
        ax3 = fig.add_subplot(gs[1, 0])
        time_points = timestamps[1:]
        ax3.plot(time_points, velocities, 'g-', linewidth=1, alpha=0.5, label='Instantaneous')

        # Calculate moving average
        window = settings.moving_average_window
        if len(velocities) >= window:
            moving_avg = np.convolve(velocities, np.ones(window)/window, mode='valid')
            # Adjust time points for moving average (centered)
            offset = (window - 1) // 2
            ma_time = time_points[offset:offset + len(moving_avg)]
            ax3.plot(ma_time, moving_avg, 'b-', linewidth=2,
                    label=f'Moving Avg (window={window})')

        ax3.axhline(y=np.mean(velocities), color='r', linestyle='--',
                   label=f'Overall Mean: {np.mean(velocities):.1f}px/s')
        ax3.axhline(y=movement_threshold, color='orange', linestyle=':',
                   label='Movement threshold')
        ax3.set_title('Movement Velocity', fontsize=13, fontweight='bold')
        ax3.set_xlabel('Time (seconds)')
        ax3.set_ylabel('Velocity (px/s)')
        ax3.grid(True, alpha=0.3)
        ax3.legend()

        # Plot 4: Velocity distribution
        ax4 = fig.add_subplot(gs[1, 1])
        ax4.hist(velocities, bins=settings.velocity_bins, alpha=0.7, color='purple', edgecolor='black')
        ax4.axvline(x=np.mean(velocities), color='r', linestyle='--',
                   label=f'Mean: {np.mean(velocities):.1f}px/s')
        ax4.axvline(x=movement_threshold, color='orange', linestyle=':',
                   label='Movement threshold')
        ax4.set_title('Velocity Distribution', fontsize=13, fontweight='bold')
        ax4.set_xlabel('Velocity (px/s)')
        ax4.set_ylabel('Frequency')
        ax4.legend()

        # Plot 5: Activity classification
        ax5 = fig.add_subplot(gs[1, 2])
        labels = ['Moving', 'Stationary']
        sizes = [1 - stationary_ratio, stationary_ratio]
        colors = ['#ff9999', '#66b3ff']
        ax5.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
        ax5.set_title('Activity Classification', fontsize=13, fontweight='bold')

        plt.tight_layout(pad=2.0)

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()

        return StreamingResponse(buf, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download")
async def download_complete_analysis(request: HeatmapRequest):
    """Generate and download complete analysis as ZIP with separate images and enhanced JSON"""
    try:
        tracking_data = request.tracking_data
        settings = request.settings

        # Extract data
        frames = []
        x_coords = []
        y_coords = []
        timestamps = []

        for frame in tracking_data.tracking_data:
            if frame.centroid_x is not None and frame.centroid_y is not None:
                frames.append(frame.frame_number)
                x_coords.append(frame.centroid_x)
                y_coords.append(frame.centroid_y)
                timestamps.append(frame.timestamp_sec)

        if len(frames) < 2:
            raise HTTPException(status_code=400, detail="Not enough tracking data")

        x_coords = np.array(x_coords)
        y_coords = np.array(y_coords)
        timestamps = np.array(timestamps)

        # Calculate metrics
        center_x = np.mean(x_coords)
        center_y = np.mean(y_coords)

        velocities = []
        for i in range(1, len(x_coords)):
            dx = x_coords[i] - x_coords[i-1]
            dy = y_coords[i] - y_coords[i-1]
            dt = timestamps[i] - timestamps[i-1]
            if dt > 0:
                distance = np.sqrt(dx**2 + dy**2)
                velocity = distance / dt
                velocities.append(velocity)
            else:
                velocities.append(0)

        velocities = np.array(velocities)
        distances_from_center = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2)
        total_distance = np.sum([np.sqrt((x_coords[i] - x_coords[i-1])**2 +
                                         (y_coords[i] - y_coords[i-1])**2)
                                 for i in range(1, len(x_coords))])
        movement_threshold = np.percentile(velocities, settings.movement_threshold_percentile)
        moving_frames = velocities > movement_threshold
        stationary_ratio = 1 - (np.sum(moving_frames) / len(moving_frames))

        # Create temporary directory for files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = TEMP_DIR / timestamp
        temp_dir.mkdir(exist_ok=True)

        # Generate individual plots
        # 1. Heatmap
        plt.figure(figsize=(12, 8))
        heatmap, _, _ = np.histogram2d(x_coords, y_coords, bins=settings.resolution, density=True)
        heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=settings.gaussian_sigma)
        extent = [min(x_coords), max(x_coords), min(y_coords), max(y_coords)]
        im = plt.imshow(heatmap_smooth.T, origin='lower', extent=extent,
                       cmap=settings.colormap, aspect='equal',
                       alpha=settings.transparency, interpolation='bilinear')
        plt.plot(x_coords, y_coords, 'k-', alpha=0.3, linewidth=0.5, label='Trajectory')
        plt.scatter(center_x, center_y, c='red', s=100, marker='x',
                   linewidth=3, label='Center of Mass')
        plt.colorbar(im, label='Movement Density')
        plt.title('Animal Movement Heatmap', fontsize=16, fontweight='bold')
        plt.xlabel('X Position (pixels)', fontsize=12)
        plt.ylabel('Y Position (pixels)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.savefig(temp_dir / '01_heatmap.png', dpi=300, bbox_inches='tight')
        plt.close()

        # 2. Velocity over time
        plt.figure(figsize=(10, 6))
        time_points = timestamps[1:]
        plt.plot(time_points, velocities, 'g-', linewidth=1, alpha=0.5, label='Instantaneous')

        # Calculate moving average
        window = settings.moving_average_window
        if len(velocities) >= window:
            moving_avg = np.convolve(velocities, np.ones(window)/window, mode='valid')
            # Adjust time points for moving average (centered)
            offset = (window - 1) // 2
            ma_time = time_points[offset:offset + len(moving_avg)]
            plt.plot(ma_time, moving_avg, 'b-', linewidth=2,
                    label=f'Moving Avg (window={window})')

        plt.axhline(y=np.mean(velocities), color='r', linestyle='--',
                   label=f'Overall Mean: {np.mean(velocities):.1f}px/s')
        plt.axhline(y=movement_threshold, color='orange', linestyle=':',
                   label='Movement threshold')
        plt.title('Movement Velocity', fontsize=16, fontweight='bold')
        plt.xlabel('Time (seconds)')
        plt.ylabel('Velocity (pixels/second)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.savefig(temp_dir / '02_velocity.png', dpi=300, bbox_inches='tight')
        plt.close()

        # 3. Velocity distribution
        plt.figure(figsize=(8, 6))
        plt.hist(velocities, bins=settings.velocity_bins, alpha=0.7, color='purple', edgecolor='black')
        plt.axvline(x=np.mean(velocities), color='r', linestyle='--',
                   label=f'Mean: {np.mean(velocities):.1f}px/s')
        plt.axvline(x=movement_threshold, color='orange', linestyle=':',
                   label='Movement threshold')
        plt.title('Velocity Distribution', fontsize=16, fontweight='bold')
        plt.xlabel('Velocity (pixels/second)')
        plt.ylabel('Frequency')
        plt.legend()
        plt.savefig(temp_dir / '03_velocity_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()

        # 4. Activity classification
        plt.figure(figsize=(8, 8))
        labels = ['Moving', 'Stationary']
        sizes = [1 - stationary_ratio, stationary_ratio]
        colors = ['#ff9999', '#66b3ff']
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
        plt.title('Activity Classification', fontsize=16, fontweight='bold')
        plt.savefig(temp_dir / '04_activity_classification.png', dpi=300, bbox_inches='tight')
        plt.close()

        # Create enhanced JSON with velocity data
        enhanced_data = {
            "video_name": tracking_data.video_name,
            "experiment_type": tracking_data.experiment_type,
            "timestamp": tracking_data.timestamp,
            "video_info": tracking_data.video_info.model_dump(),
            "statistics": tracking_data.statistics.model_dump(),
            "analysis_summary": {
                "center_of_mass": {"x": float(center_x), "y": float(center_y)},
                "total_distance": float(total_distance),
                "duration_sec": float(timestamps[-1] - timestamps[0]),
                "mean_velocity": float(np.mean(velocities)),
                "max_velocity": float(np.max(velocities)),
                "min_velocity": float(np.min(velocities)),
                "movement_threshold": float(movement_threshold),
                "stationary_ratio": float(stationary_ratio),
                "moving_ratio": float(1 - stationary_ratio)
            },
            "rois": [roi.model_dump() for roi in tracking_data.rois],
            "tracking_data_with_velocity": []
        }

        # Add velocity to each frame
        for i, frame in enumerate(tracking_data.tracking_data):
            frame_data = frame.model_dump()
            # Add velocity (0 for first frame, calculated for others)
            if i > 0 and i-1 < len(velocities):
                frame_data["velocity"] = float(velocities[i-1])
            else:
                frame_data["velocity"] = 0.0
            enhanced_data["tracking_data_with_velocity"].append(frame_data)

        # Save enhanced JSON
        json_path = temp_dir / 'analysis_data_with_velocity.json'
        with open(json_path, 'w') as f:
            json.dump(enhanced_data, f, indent=2)

        # Create ZIP file
        zip_path = TEMP_DIR / f'analysis_{timestamp}.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in temp_dir.iterdir():
                zipf.write(file_path, file_path.name)

        # Clean up temp directory
        for file_path in temp_dir.iterdir():
            file_path.unlink()
        temp_dir.rmdir()

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"complete_analysis_{timestamp}.zip"
        )

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
