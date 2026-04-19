"""Analysis API endpoints"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch
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

        # Calculate proper extent from actual data
        extent = [min(x_coords), max(x_coords), min(y_coords), max(y_coords)]

        # Normalize heatmap to 0-1 range first
        heatmap_max = heatmap_smooth.max()
        if heatmap_max > 0:
            heatmap_normalized = heatmap_smooth / heatmap_max
        else:
            heatmap_normalized = heatmap_smooth

        # Use PowerNorm to enhance low-density areas (gamma < 1 expands low values)
        # This makes areas with less movement more visible
        norm = mcolors.PowerNorm(gamma=0.4, vmin=0, vmax=1)

        # Plot smoothed heatmap with power normalization
        im = ax.imshow(
            heatmap_normalized.T,
            origin='lower',
            extent=extent,
            cmap=settings.colormap,
            aspect='equal',
            alpha=settings.transparency,
            interpolation='bilinear',
            norm=norm
        )

        # Plot trajectory overlay (using trajectory settings)
        trajectory = request.options.trajectory if request.options else None
        if trajectory is None or trajectory.show_trajectory:
            traj_color = trajectory.color if trajectory else 'white'
            traj_alpha = trajectory.alpha if trajectory else 0.4
            traj_width = trajectory.width if trajectory else 1.0
            ax.plot(x_coords, y_coords, color=traj_color, alpha=traj_alpha,
                    linewidth=traj_width, label='Trajectory')

        # Colorbar with exact plot height using make_axes_locatable
        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="3%", pad=0.1)
        cbar = plt.colorbar(im, cax=cax, label='Density (norm.)')
        cbar.set_ticks([0, 1.0])
        cbar.set_ticklabels(['0', '1'])

        ax.set_xlabel('X Position (pixels)', fontsize=12)
        ax.set_ylabel('Y Position (pixels)', fontsize=12)
        ax.set_title('Animal Movement Heatmap', fontsize=16, fontweight='bold')

        # Discrete and transparent legend (only if trajectory is shown)
        trajectory = request.options.trajectory if request.options else None
        if trajectory is None or trajectory.show_trajectory:
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
        
        # Add moving average if window allows
        window = settings.moving_average_window
        if len(velocities) >= window:
            moving_avg = np.convolve(velocities, np.ones(window)/window, mode='valid')
            offset = (window - 1) // 2
            ma_time = time_points[offset:offset + len(moving_avg)]
            ax1.plot(ma_time, moving_avg, 'b-', linewidth=2,
                    label=f'Moving Avg (window={window})')

        ax1.set_title('Movement Velocity Over Time', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Time (seconds)', fontsize=12)
        ax1.set_ylabel('Velocity (pixels/second)', fontsize=12)
        ax1.grid(False)
        ax1.legend()

        # Plot 2: Activity classification
        ax3 = fig.add_subplot(gs[1, :])
        ax3.step(time_points, moving_frames.astype(int), color='#2c3e50', linewidth=1.5, where='post')
        ax3.fill_between(time_points, 0, moving_frames.astype(int), step='post', alpha=0.3, color='#e74c3c')
        ax3.set_yticks([0, 1])
        ax3.set_yticklabels(['Stationary', 'Moving'])
        
        moving_pct = (1 - stationary_ratio) * 100
        stat_pct = stationary_ratio * 100
        ax3.set_title(f'Activity Ethogram\nMoving: {moving_pct:.1f}% | Stationary: {stat_pct:.1f}%', fontsize=13, fontweight='bold')
        ax3.set_xlabel('Time (seconds)')
        ax3.set_ylim(-0.2, 1.2)

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


def draw_heatmap(ax, x_coords, y_coords, settings, title, background_img=None, options=None):
    """Helper function to draw heatmap on an axis"""
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

    # Use PowerNorm to enhance low-density areas
    norm = mcolors.PowerNorm(gamma=0.4, vmin=0, vmax=1)

    im = ax.imshow(
        heatmap_normalized.T,
        origin='lower',
        extent=extent,
        cmap=settings.colormap,
        aspect='equal',
        alpha=settings.transparency,
        interpolation='bilinear',
        norm=norm
    )

    # Trajectory settings
    trajectory = options.trajectory if options else None
    traj_show = trajectory.show_trajectory if trajectory else True
    if traj_show:
        traj_color = trajectory.color if trajectory else 'white'
        traj_alpha = trajectory.alpha if trajectory else 0.4
        traj_width = trajectory.width if trajectory else 1.0
        ax.plot(x_coords, y_coords, color=traj_color, alpha=traj_alpha,
                linewidth=traj_width, label='Trajectory')

    # Colorbar
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="3%", pad=0.1)
    cbar = plt.colorbar(im, cax=cax, label='Density (norm.)')
    cbar.set_ticks([0, 1.0])
    cbar.set_ticklabels(['0', '1'])

    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlabel('X Position (px)', fontsize=12)
    ax.set_ylabel('Y Position (px)', fontsize=12)
    if traj_show:
        ax.legend(loc='upper right', framealpha=0.5, fontsize=9, fancybox=True, edgecolor='gray')


def create_heatmap_figure(x_coords, y_coords, settings, title, background_img=None, options=None):
    """Helper function to create a complete heatmap figure"""
    fig, ax = plt.subplots(figsize=(12, 8))
    draw_heatmap(ax, x_coords, y_coords, settings, title, background_img, options)
    return fig


@router.post("/complete")
async def generate_complete_analysis(request: HeatmapRequest):
    """Generate analysis panel with only selected analyses"""
    try:
        tracking_data = request.tracking_data
        settings = request.settings
        options = request.options

        # Get which analyses to include
        include_heatmap = options.heatmap
        include_velocity = options.velocity
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

        # Calculate velocity slots
        velocity_count = 1 if include_velocity else 0

        # Count selected analyses
        selected_count = heatmap_count + velocity_count + (1 if include_activity else 0)

        if selected_count == 0:
            raise HTTPException(status_code=400, detail="At least one analysis must be selected")

        # Decode background image if provided
        background_img = None
        if request.video_frame_base64 and show_with_overlay:
            try:
                img_data = base64.b64decode(request.video_frame_base64.split(',')[-1])
                background_img = np.array(Image.open(io.BytesIO(img_data)))
            except Exception as e:
                print(f"Failed to decode background image: {e}")

        # Determine layout based on selected analyses
        if selected_count == 1:
            fig, ax = plt.subplots(figsize=(12, 8))
            axes = [ax]
        elif selected_count == 2:
            fig, axes = plt.subplots(1, 2, figsize=(18, 8))
        elif selected_count == 3:
            fig = plt.figure(figsize=(18, 12))
            if include_heatmap:
                gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1], hspace=0.3, wspace=0.25)
                axes = [fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]
            else:
                gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.25)
                axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, 0])]
        else:
            cols = 2
            rows = (selected_count + cols - 1) // cols
            fig = plt.figure(figsize=(20, 7 * rows))
            gs = fig.add_gridspec(rows, cols, hspace=0.3, wspace=0.25)
            axes = [fig.add_subplot(gs[i // cols, i % cols]) for i in range(selected_count)]

        # Extract data into NumPy arrays for high-performance vectorization
        # Use a more direct way to extract coordinates to save memory
        coords_list = [[f.centroid_x, f.centroid_y, f.timestamp_sec] 
                      for f in tracking_data.tracking_data 
                      if f.centroid_x is not None and f.centroid_y is not None]
        
        if len(coords_list) < 2:
            raise HTTPException(status_code=400, detail="Not enough tracking data")
            
        data_arr = np.array(coords_list, dtype=np.float32)
        x_coords = data_arr[:, 0]
        y_coords = data_arr[:, 1]
        timestamps = data_arr[:, 2]
        del coords_list # Free memory

        # Vectorized metrics calculation
        dx = np.diff(x_coords)
        dy = np.diff(y_coords)
        dt = np.diff(timestamps)
        
        dist_consecutive = np.sqrt(dx**2 + dy**2)
        total_distance = np.sum(dist_consecutive)
        
        # Safe velocity calculation
        safe_dt = np.where(dt > 0, dt, 1.0)
        velocities = np.where(dt > 0, dist_consecutive / safe_dt, 0.0)
        time_points = timestamps[1:]
        
        # Calculate threshold and moving average
        movement_threshold = np.percentile(velocities, settings.movement_threshold_percentile) if len(velocities) > 0 else 0
        window = settings.moving_average_window
        
        if window > 1 and len(velocities) >= window:
            moving_avg = np.convolve(velocities, np.ones(window)/window, mode='valid')
            offset = (window - 1) // 2
            ma_time = time_points[offset:offset + len(moving_avg)]
        else:
            moving_avg = velocities
            ma_time = time_points

        # Track which axis to use
        ax_idx = 0

        # Plot Heatmap(s)
        if include_heatmap:
            if show_heatmap_only:
                ax = axes[ax_idx]
                ax_idx += 1
                draw_heatmap(ax, x_coords, y_coords, settings, 'Animal Movement Heatmap', options=options)

            if show_with_overlay and background_img is not None:
                ax = axes[ax_idx]
                ax_idx += 1
                draw_heatmap(ax, x_coords, y_coords, settings, 'Heatmap with Original Image', background_img, options=options)

        # Plot Velocity
        if include_velocity:
            ax = axes[ax_idx]
            ax_idx += 1
            title = f'Movement Velocity (Window={window})' if window > 1 else 'Instantaneous Velocity'
            
            # Use charcoal gray (#2d3436) for a professional scientific look (no blue)
            v_color = '#2d3436'
            
            # Subsample plot if points are excessive (>100k) for SVG/Render performance
            if len(ma_time) > 100000:
                step = len(ma_time) // 50000
                ax.plot(ma_time[::step], moving_avg[::step], color=v_color, linewidth=1.0, alpha=0.8)
            else:
                ax.plot(ma_time, moving_avg, color=v_color, linewidth=1.0, alpha=0.8)
                
            ax.set_title(title, fontsize=13, fontweight='bold', pad=10)
            ax.set_xlabel('Time (seconds)', fontsize=10)
            ax.set_ylabel('Velocity (px/s)', fontsize=10)
            
            # Standardized minimalist style
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(axis='y', alpha=0.15, linestyle='--')

        # Plot Activity Analysis (Refined Scientific Histogram)
        if include_activity:
            ax = axes[ax_idx]
            ax_idx += 1
            
            # Filter extreme outliers (99th percentile)
            if len(velocities) > 0:
                v_limit = np.percentile(velocities, 99)
                v_filtered = velocities[velocities <= v_limit]
            else:
                v_limit = 100
                v_filtered = velocities

            t1 = movement_threshold
            t2 = np.percentile(velocities, 90) if len(velocities) > 0 else t1 * 2
            if t2 <= t1: t2 = t1 * 1.5

            total = len(velocities)
            p_stat = np.sum(velocities < t1) / total * 100
            p_slow = np.sum((velocities >= t1) & (velocities < t2)) / total * 100
            p_fast = np.sum(velocities >= t2) / total * 100

            n, bins, patches = ax.hist(v_filtered, bins=settings.velocity_bins, density=True, alpha=0.7, edgecolor='white', linewidth=0.3)
            
            for i in range(len(patches)):
                mid_bin = (bins[i] + bins[i+1]) / 2
                if mid_bin < t1:
                    patches[i].set_facecolor('#34495e') # Stationary
                elif mid_bin < t2:
                    patches[i].set_facecolor('#f39c12') # Ambulatory
                else:
                    patches[i].set_facecolor('#e74c3c') # Fast

            # Add smooth KDE overlay - SAMPLING for performance if points > 50k
            if len(v_filtered) > 1:
                try:
                    from scipy.stats import gaussian_kde
                    if len(v_filtered) > 50000:
                        kde_sample = np.random.choice(v_filtered, 50000, replace=False)
                    else:
                        kde_sample = v_filtered
                        
                    kde = gaussian_kde(kde_sample)
                    x_range = np.linspace(0, v_limit, 200)
                    ax.plot(x_range, kde(x_range), color='black', linewidth=1.2, alpha=0.8, label='Trend')
                except: pass

            ax.axvline(t1, color='black', linestyle='--', linewidth=1, alpha=0.4)
            ax.axvline(t2, color='black', linestyle=':', linewidth=1, alpha=0.4)

            ax.set_title('Behavioral Activity Distribution', fontsize=14, fontweight='bold', pad=10)
            ax.set_xlabel('Velocity (px/s)', fontsize=10)
            ax.set_ylabel('Probability Density', fontsize=10)
            
            legend_elements = [
                Patch(facecolor='#34495e', label=f'Stationary: {p_stat:.1f}%'),
                Patch(facecolor='#f39c12', label=f'Ambulatory: {p_slow:.1f}%'),
                Patch(facecolor='#e74c3c', label=f'Active/Fast: {p_fast:.1f}%')
            ]
            ax.legend(handles=legend_elements, loc='upper right', frameon=True, fontsize=8)
            
            # Standardized minimalist style
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(axis='y', alpha=0.15, linestyle='--')

        plt.tight_layout(pad=2.0)

        # Save to buffer - Lower DPI for preview performance
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return StreamingResponse(buf, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download")
async def download_complete_analysis(request: HeatmapRequest):
    """Generate and download complete analysis as ZIP with separate images and enhanced JSON"""
    try:
        tracking_data = request.tracking_data
        settings = request.settings

        # Extract data into NumPy arrays for high-performance vectorization
        valid_data = [(f.centroid_x, f.centroid_y, f.timestamp_sec) 
                     for f in tracking_data.tracking_data 
                     if f.centroid_x is not None and f.centroid_y is not None]
        
        if len(valid_data) < 2:
            raise HTTPException(status_code=400, detail="Not enough tracking data")
            
        data_arr = np.array(valid_data)
        x_coords = data_arr[:, 0]
        y_coords = data_arr[:, 1]
        timestamps = data_arr[:, 2]

        # Vectorized metrics calculation
        dx = np.diff(x_coords)
        dy = np.diff(y_coords)
        dt = np.diff(timestamps)
        
        dist_consecutive = np.sqrt(dx**2 + dy**2)
        total_distance = np.sum(dist_consecutive)
        
        # Safe velocity calculation
        safe_dt = np.where(dt > 0, dt, 1.0)
        velocities = np.where(dt > 0, dist_consecutive / safe_dt, 0.0)
        time_points = timestamps[1:]
        
        # Calculate threshold and moving average
        movement_threshold = np.percentile(velocities, settings.movement_threshold_percentile) if len(velocities) > 0 else 0
        window = settings.moving_average_window
        
        if window > 1 and len(velocities) >= window:
            moving_avg = np.convolve(velocities, np.ones(window)/window, mode='valid')
            offset = (window - 1) // 2
            ma_time = time_points[offset:offset + len(moving_avg)]
        else:
            moving_avg = velocities
            ma_time = time_points

        # Create temporary directory for files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = TEMP_DIR / timestamp
        temp_dir.mkdir(exist_ok=True)

        # Get analysis options (with defaults for backwards compatibility)
        options = request.options if hasattr(request, 'options') else None
        include_heatmap = options.heatmap if options else True
        include_velocity = options.velocity if options else True
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

        # Helper function to draw heatmap (shared)
        # (Assuming draw_heatmap and create_heatmap_figure are available or need re-definition if changed)

        # Generate individual plots based on selected options
        file_idx = 0

        # 1. Heatmap Only
        if include_heatmap and show_heatmap_only:
            file_idx += 1
            fig = create_heatmap_figure(x_coords, y_coords, settings, 'Animal Movement Heatmap', options=options)
            save_plot(fig, str(temp_dir / f'{file_idx:02d}_heatmap'))
            plt.close(fig)

        # 2. Heatmap with Overlay
        if include_heatmap and show_with_overlay and background_img is not None:
            file_idx += 1
            fig = create_heatmap_figure(x_coords, y_coords, settings, 'Heatmap with Original Image', background_img, options=options)
            save_plot(fig, str(temp_dir / f'{file_idx:02d}_heatmap_overlay'))
            plt.close(fig)

        # 3. Velocity
        if include_velocity:
            file_idx += 1
            fig = plt.figure(figsize=(10, 6))
            ax = fig.gca()
            
            # Use charcoal gray (#2d3436) for professional look (no blue)
            v_color = '#2d3436'
            
            # Subsample plot if points are excessive (>100k) for SVG performance
            if len(ma_time) > 100000:
                step = len(ma_time) // 50000
                ax.plot(ma_time[::step], moving_avg[::step], color=v_color, linewidth=1.0, alpha=0.8)
            else:
                ax.plot(ma_time, moving_avg, color=v_color, linewidth=1.0, alpha=0.8)
                
            title = f'Movement Velocity (Window={window})' if window > 1 else 'Instantaneous Velocity'
            ax.set_title(title, fontsize=16, fontweight='bold', pad=15)
            ax.set_xlabel('Time (seconds)', fontsize=12)
            ax.set_ylabel('Velocity (px/s)', fontsize=12)
            
            # Minimalist scientific style
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(axis='y', alpha=0.15, linestyle='--')
            
            save_plot(fig, str(temp_dir / f'{file_idx:02d}_velocity'))
            plt.close(fig)

        # 5. Activity Analysis (Refined Scientific Histogram)
        if include_activity:
            file_idx += 1
            fig, ax = plt.subplots(figsize=(10, 6))
            
            if len(velocities) > 0:
                v_limit = np.percentile(velocities, 99)
                v_filtered = velocities[velocities <= v_limit]
            else:
                v_filtered = velocities

            t1 = movement_threshold
            t2 = np.percentile(velocities, 90) if len(velocities) > 0 else t1 * 2
            if t2 <= t1: t2 = t1 * 1.5

            total = len(velocities)
            p_stat = np.sum(velocities < t1) / total * 100
            p_slow = np.sum((velocities >= t1) & (velocities < t2)) / total * 100
            p_fast = np.sum(velocities >= t2) / total * 100

            n, bins, patches = ax.hist(v_filtered, bins=settings.velocity_bins, density=True, alpha=0.7, edgecolor='white', linewidth=0.5)
            
            for i in range(len(patches)):
                mid_bin = (bins[i] + bins[i+1]) / 2
                if mid_bin < t1:
                    patches[i].set_facecolor('#34495e')
                elif mid_bin < t2:
                    patches[i].set_facecolor('#f39c12')
                else:
                    patches[i].set_facecolor('#e74c3c')

            if len(v_filtered) > 1:
                try:
                    from scipy.stats import gaussian_kde
                    if len(v_filtered) > 50000:
                        kde_sample = np.random.choice(v_filtered, 50000, replace=False)
                    else:
                        kde_sample = v_filtered
                    kde = gaussian_kde(kde_sample)
                    x_range = np.linspace(0, v_limit, 300)
                    ax.plot(x_range, kde(x_range), color='black', linewidth=1.2, alpha=0.8, label='Trend')
                except: pass

            ax.axvline(t1, color='black', linestyle='--', linewidth=1, alpha=0.5)
            ax.axvline(t2, color='black', linestyle=':', linewidth=1, alpha=0.5)

            ax.set_title('Behavioral Activity Distribution', fontsize=16, fontweight='bold', pad=15)
            ax.set_xlabel('Velocity (px/s)', fontsize=12)
            ax.set_ylabel('Probability Density', fontsize=12)
            
            legend_elements = [
                Patch(facecolor='#34495e', label=f'Stationary: {p_stat:.1f}%'),
                Patch(facecolor='#f39c12', label=f'Ambulatory: {p_slow:.1f}%'),
                Patch(facecolor='#e74c3c', label=f'Active/Fast: {p_fast:.1f}%')
            ]
            ax.legend(handles=legend_elements, loc='upper right', frameon=True, fontsize=10)
            
            # Minimalist scientific style
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(axis='y', alpha=0.15, linestyle='--')
            
            save_plot(fig, str(temp_dir / f'{file_idx:02d}_activity_analysis'))
            plt.close(fig)

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
