"""Analysis API endpoints"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import scipy.ndimage as ndimage
import io
import json
import zipfile
import tempfile
import os
import base64
from pathlib import Path
from datetime import datetime
from PIL import Image

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


@router.get("/load-large-json")
async def load_large_json(file_path: str):
    """
    Load a large JSON file directly from the server's disk.
    This bypasses browser memory limits for very large tracking files.
    """
    try:
        # Check if path is absolute or relative to project root
        path = Path(file_path)
        if not path.exists():
            # Try relative to current directory
            path = Path(os.getcwd()) / file_path

        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        # Verify it's a JSON file
        if not path.suffix.lower() == '.json':
            raise HTTPException(status_code=400, detail="Only JSON files are supported")

        # Check file size
        file_size = path.stat().st_size
        print(f"Loading large JSON: {path} ({file_size / 1024 / 1024:.2f} MB)")

        # We use a stream or just read and return.
        # For FastAPI, returning a large dict is fine as it's handled server-side.
        with open(path, 'r') as f:
            data = json.load(f)

        return ApiResponse(success=True, data=data)

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
    except Exception as e:
        print(f"Error loading large JSON: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-large-json")
async def upload_large_json(file: UploadFile = File(...)):
    """
    Upload a large JSON file via multipart form and process it server-side.
    This handles large files that would crash the browser's JSON.parse.
    """
    try:
        file_size = 0
        # Save to temp file first to get size and enable streaming
        temp_path = TEMP_DIR / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"

        # Stream write to disk
        with open(temp_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(content)
                out_file.write(content)

        print(f"Uploaded large JSON: {temp_path} ({file_size / 1024 / 1024:.2f} MB)")

        # Now parse the JSON from the temp file
        with open(temp_path, 'r') as f:
            data = json.load(f)

        # Clean up temp file
        temp_path.unlink()

        return ApiResponse(success=True, data=data, message=f"Loaded {file_size / 1024 / 1024:.2f} MB")

    except json.JSONDecodeError as e:
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
    except Exception as e:
        print(f"Error uploading large JSON: {e}")
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))


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
            density=True
        )

        # Apply Gaussian smoothing for better visualization
        heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=settings.gaussian_sigma)

        # Normalize heatmap to 0-1 range
        heatmap_max = heatmap_smooth.max()
        if heatmap_max > 0:
            heatmap_normalized = heatmap_smooth / heatmap_max
        else:
            heatmap_normalized = heatmap_smooth

        # Calculate proper extent from actual data
        extent = [min(x_coords), max(x_coords), min(y_coords), max(y_coords)]

        # Plot smoothed heatmap with normalized values
        im = ax.imshow(
            heatmap_normalized.T,
            origin='lower',
            extent=extent,
            cmap=settings.colormap,
            aspect='equal',
            alpha=settings.transparency,
            interpolation='bilinear',
            vmin=0, vmax=1
        )

        # Plot trajectory overlay
        ax.plot(x_coords, y_coords, 'k-', alpha=0.3, linewidth=0.5, label='Trajectory')

        # Colorbar with exact plot height using make_axes_locatable
        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="3%", pad=0.1)
        cbar = plt.colorbar(im, cax=cax, label='Density (norm.)')
        cbar.set_ticks([0, 0.25, 0.5, 0.75, 1.0])
        cbar.set_ticklabels(['0.0', '0.25', '0.5', '0.75', '1.0'])

        ax.set_xlabel('X Position (pixels)', fontsize=12)
        ax.set_ylabel('Y Position (pixels)', fontsize=12)
        ax.set_title('Animal Movement Heatmap', fontsize=16, fontweight='bold')

        # Discrete and transparent legend
        ax.legend(loc='upper right', framealpha=0.5, fontsize=9, fancybox=True, edgecolor='gray')

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
    """Generate analysis panel with only selected analyses"""
    try:
        tracking_data = request.tracking_data
        settings = request.settings
        options = request.options

        # Get which analyses to include
        include_heatmap = options.heatmap
        include_velocity_time = options.velocity_over_time
        include_velocity_dist = options.velocity_distribution
        include_activity = options.activity_classification

        # Heatmap display options
        heatmap_display = options.heatmap_display
        show_heatmap_only = heatmap_display.show_heatmap_only if heatmap_display else True
        show_with_overlay = heatmap_display.show_with_overlay if heatmap_display else False

        # If both heatmap options are selected, we need 2 heatmap slots
        heatmap_count = 0
        if include_heatmap:
            if show_heatmap_only:
                heatmap_count += 1
            if show_with_overlay and request.video_frame_base64:
                heatmap_count += 1

        # Count selected analyses (heatmap counts as potentially 2)
        selected_count = heatmap_count + sum([include_velocity_time, include_velocity_dist, include_activity])

        if selected_count == 0:
            raise HTTPException(status_code=400, detail="At least one analysis must be selected")

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

        # Determine layout based on selected analyses
        if selected_count == 1:
            # Single analysis - simple layout
            fig, ax = plt.subplots(figsize=(12, 8))
            axes = [ax]
        elif selected_count == 2:
            # Two analyses - side by side
            fig, axes = plt.subplots(1, 2, figsize=(18, 8))
        elif selected_count == 3:
            # Three analyses - 2 columns, one spanning
            fig = plt.figure(figsize=(18, 12))
            if include_heatmap:
                # Heatmap on top, others below
                gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1], hspace=0.3, wspace=0.25)
                axes = [fig.add_subplot(gs[0, :])]  # Heatmap spans top
                axes.append(fig.add_subplot(gs[1, 0]))
                axes.append(fig.add_subplot(gs[1, 1]))
            else:
                gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.25)
                axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, 0])]
        else:
            # All four analyses
            fig = plt.figure(figsize=(20, 14))
            gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1], hspace=0.3, wspace=0.25)
            axes = [
                fig.add_subplot(gs[0, 0]),  # Heatmap
                fig.add_subplot(gs[0, 1]),  # Velocity over time
                fig.add_subplot(gs[1, 0]),  # Velocity distribution
                fig.add_subplot(gs[1, 1])   # Activity classification
            ]

        # Track which axis to use
        ax_idx = 0

        # Helper function to draw heatmap on an axis
        def draw_heatmap(ax, x_coords, y_coords, settings, title, background_img=None):
            heatmap, _, _ = np.histogram2d(x_coords, y_coords, bins=settings.resolution, density=True)
            heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=settings.gaussian_sigma)

            # Normalize heatmap to 0-1 range
            heatmap_max = heatmap_smooth.max()
            if heatmap_max > 0:
                heatmap_normalized = heatmap_smooth / heatmap_max
            else:
                heatmap_normalized = heatmap_smooth

            extent = [min(x_coords), max(x_coords), min(y_coords), max(y_coords)]

            # Draw background image if provided
            if background_img is not None:
                ax.imshow(background_img, extent=extent, aspect='equal', alpha=0.7)

            im = ax.imshow(
                heatmap_normalized.T,
                origin='lower',
                extent=extent,
                cmap=settings.colormap,
                aspect='equal',
                alpha=settings.transparency,
                interpolation='bilinear',
                vmin=0, vmax=1
            )

            # Trajectory with discrete legend
            ax.plot(x_coords, y_coords, 'k-', alpha=0.3, linewidth=0.5, label='Trajectory')

            # Colorbar with exact plot height
            divider = make_axes_locatable(ax)
            cax = divider.append_axes("right", size="3%", pad=0.1)
            cbar = plt.colorbar(im, cax=cax, label='Density (norm.)')
            cbar.set_ticks([0, 0.25, 0.5, 0.75, 1.0])
            cbar.set_ticklabels(['0.0', '0.25', '0.5', '0.75', '1.0'])

            ax.set_title(title, fontsize=16, fontweight='bold')
            ax.set_xlabel('X Position (pixels)', fontsize=12)
            ax.set_ylabel('Y Position (pixels)', fontsize=12)
            ax.legend(loc='upper right', framealpha=0.5, fontsize=9, fancybox=True, edgecolor='gray')

        # Decode background image if provided
        background_img = None
        if request.video_frame_base64 and show_with_overlay:
            try:
                img_data = base64.b64decode(request.video_frame_base64.split(',')[-1])
                background_img = np.array(Image.open(io.BytesIO(img_data)))
            except Exception as e:
                print(f"Failed to decode background image: {e}")

        # Plot Heatmap(s)
        if include_heatmap:
            # Heatmap Only
            if show_heatmap_only:
                ax = axes[ax_idx]
                ax_idx += 1
                draw_heatmap(ax, x_coords, y_coords, settings, 'Animal Movement Heatmap')

            # Heatmap with Overlay
            if show_with_overlay and background_img is not None:
                ax = axes[ax_idx]
                ax_idx += 1
                draw_heatmap(ax, x_coords, y_coords, settings, 'Heatmap with Original Image', background_img)

        # Plot Velocity over time
        if include_velocity_time:
            ax = axes[ax_idx]
            ax_idx += 1

            time_points = timestamps[1:]
            ax.plot(time_points, velocities, 'g-', linewidth=1, alpha=0.5, label='Instantaneous')

            # Calculate moving average
            window = settings.moving_average_window
            if len(velocities) >= window:
                moving_avg = np.convolve(velocities, np.ones(window)/window, mode='valid')
                offset = (window - 1) // 2
                ma_time = time_points[offset:offset + len(moving_avg)]
                ax.plot(ma_time, moving_avg, 'b-', linewidth=2,
                        label=f'Moving Avg (window={window})')

            ax.axhline(y=np.mean(velocities), color='r', linestyle='--',
                       label=f'Overall Mean: {np.mean(velocities):.1f}px/s')
            ax.axhline(y=movement_threshold, color='orange', linestyle=':',
                       label='Movement threshold')
            ax.set_title('Movement Velocity', fontsize=13, fontweight='bold')
            ax.set_xlabel('Time (seconds)')
            ax.set_ylabel('Velocity (px/s)')
            ax.grid(True, alpha=0.3)
            ax.legend()

        # Plot Velocity distribution
        if include_velocity_dist:
            ax = axes[ax_idx]
            ax_idx += 1

            ax.hist(velocities, bins=settings.velocity_bins, alpha=0.7, color='purple', edgecolor='black')
            ax.axvline(x=np.mean(velocities), color='r', linestyle='--',
                       label=f'Mean: {np.mean(velocities):.1f}px/s')
            ax.axvline(x=movement_threshold, color='orange', linestyle=':',
                       label='Movement threshold')
            ax.set_title('Velocity Distribution', fontsize=13, fontweight='bold')
            ax.set_xlabel('Velocity (px/s)')
            ax.set_ylabel('Frequency')
            ax.legend()

        # Plot Activity classification
        if include_activity:
            ax = axes[ax_idx]
            ax_idx += 1

            labels = ['Moving', 'Stationary']
            sizes = [1 - stationary_ratio, stationary_ratio]
            colors = ['#ff9999', '#66b3ff']
            ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
            ax.set_title('Activity Classification', fontsize=13, fontweight='bold')

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

        # Get analysis options (with defaults for backwards compatibility)
        options = request.options if hasattr(request, 'options') else None
        include_heatmap = options.heatmap if options else True
        include_velocity_time = options.velocity_over_time if options else True
        include_velocity_dist = options.velocity_distribution if options else True
        include_activity = options.activity_classification if options else True

        # Heatmap display options
        heatmap_display = options.heatmap_display if options else None
        show_heatmap_only = heatmap_display.show_heatmap_only if heatmap_display else True
        show_with_overlay = heatmap_display.show_with_overlay if heatmap_display else False

        # Decode background image if provided
        background_img = None
        if request.video_frame_base64 and show_with_overlay:
            try:
                img_data = base64.b64decode(request.video_frame_base64.split(',')[-1])
                background_img = np.array(Image.open(io.BytesIO(img_data)))
            except Exception as e:
                print(f"Failed to decode background image: {e}")

        # Helper function to save plot in multiple formats
        def save_plot(fig, base_path):
            fig.savefig(f'{base_path}.png', dpi=300, bbox_inches='tight')
            fig.savefig(f'{base_path}.svg', format='svg', bbox_inches='tight')

        # Helper function to draw heatmap
        def create_heatmap_figure(x_coords, y_coords, settings, title, background_img=None):
            fig, ax = plt.subplots(figsize=(12, 8))

            heatmap, _, _ = np.histogram2d(x_coords, y_coords, bins=settings.resolution, density=True)
            heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=settings.gaussian_sigma)

            # Normalize heatmap to 0-1 range
            heatmap_max = heatmap_smooth.max()
            if heatmap_max > 0:
                heatmap_normalized = heatmap_smooth / heatmap_max
            else:
                heatmap_normalized = heatmap_smooth

            extent = [min(x_coords), max(x_coords), min(y_coords), max(y_coords)]

            # Draw background image if provided
            if background_img is not None:
                ax.imshow(background_img, extent=extent, aspect='equal', alpha=0.7)

            im = ax.imshow(heatmap_normalized.T, origin='lower', extent=extent,
                           cmap=settings.colormap, aspect='equal',
                           alpha=settings.transparency, interpolation='bilinear',
                           vmin=0, vmax=1)

            # Trajectory with discrete legend
            ax.plot(x_coords, y_coords, 'k-', alpha=0.3, linewidth=0.5, label='Trajectory')

            # Colorbar with exact plot height
            divider = make_axes_locatable(ax)
            cax = divider.append_axes("right", size="3%", pad=0.1)
            cbar = fig.colorbar(im, cax=cax, label='Density (norm.)')
            cbar.set_ticks([0, 0.25, 0.5, 0.75, 1.0])
            cbar.set_ticklabels(['0.0', '0.25', '0.5', '0.75', '1.0'])

            ax.set_title(title, fontsize=16, fontweight='bold')
            ax.set_xlabel('X Position (pixels)', fontsize=12)
            ax.set_ylabel('Y Position (pixels)', fontsize=12)
            ax.legend(loc='upper right', framealpha=0.5, fontsize=9, fancybox=True, edgecolor='gray')

            return fig

        # Generate individual plots based on selected options
        plot_count = 0

        # 1. Heatmap Only
        if include_heatmap and show_heatmap_only:
            plot_count += 1
            fig = create_heatmap_figure(x_coords, y_coords, settings, 'Animal Movement Heatmap')
            save_plot(fig, str(temp_dir / f'{plot_count:02d}_heatmap'))
            plt.close(fig)

        # 2. Heatmap with Overlay
        if include_heatmap and show_with_overlay and background_img is not None:
            plot_count += 1
            fig = create_heatmap_figure(x_coords, y_coords, settings, 'Heatmap with Original Image', background_img)
            save_plot(fig, str(temp_dir / f'{plot_count:02d}_heatmap_overlay'))
            plt.close(fig)

        # 3. Velocity over time
        if include_velocity_time:
            plot_count += 1
            fig = plt.figure(figsize=(10, 6))
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
            save_plot(fig, str(temp_dir / f'{plot_count:02d}_velocity'))
            plt.close()

        # 4. Velocity distribution
        if include_velocity_dist:
            plot_count += 1
            fig = plt.figure(figsize=(8, 6))
            plt.hist(velocities, bins=settings.velocity_bins, alpha=0.7, color='purple', edgecolor='black')
            plt.axvline(x=np.mean(velocities), color='r', linestyle='--',
                       label=f'Mean: {np.mean(velocities):.1f}px/s')
            plt.axvline(x=movement_threshold, color='orange', linestyle=':',
                       label='Movement threshold')
            plt.title('Velocity Distribution', fontsize=16, fontweight='bold')
            plt.xlabel('Velocity (pixels/second)')
            plt.ylabel('Frequency')
            plt.legend()
            save_plot(fig, str(temp_dir / f'{plot_count:02d}_velocity_distribution'))
            plt.close()

        # 5. Activity classification
        if include_activity:
            plot_count += 1
            fig = plt.figure(figsize=(8, 8))
            labels = ['Moving', 'Stationary']
            sizes = [1 - stationary_ratio, stationary_ratio]
            colors = ['#ff9999', '#66b3ff']
            plt.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
            plt.title('Activity Classification', fontsize=16, fontweight='bold')
            save_plot(fig, str(temp_dir / f'{plot_count:02d}_activity_classification'))
            plt.close()

        # Create ZIP file (images only, no JSON)
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
