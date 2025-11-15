import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Callable

import panel as pn

from .tracking_visualizer import TrackingVisualizer


class VideoAnalysis:
    """Handles video analysis operations for ethological analysis"""

    def __init__(self, temp_dir: Path, project_root: Path) -> None:
        self.temp_dir = temp_dir
        self.project_root = project_root
        self.analysis_process = None
        self.is_analyzing = False
        self.current_output_path = None

    def start_analysis(
        self,
        video_value: bytes,
        json_value: bytes,
        video_filename: str,
        json_filename: str,
        show_info: bool,
        show_heatmap: bool,
        progress_callback: Callable[[int], None],
        status_callback: Callable[[str, str], None],
        download_widget,
    ) -> None:
        """Start video analysis in background thread"""
        if not video_value or not json_value:
            return

        # Start analysis mode
        self.is_analyzing = True

        status_callback(
            "**Status:** 🔄 Starting video analysis...\n\nInitializing analysis process...",
            "#fff3cd",
        )

        # Run analysis in background thread
        analysis_thread = threading.Thread(
            target=self._run_analysis,
            args=(
                video_value,
                json_value,
                video_filename,
                json_filename,
                show_info,
                show_heatmap,
                progress_callback,
                status_callback,
                download_widget,
            ),
            daemon=True,
        )
        analysis_thread.start()

    def abort_analysis(self) -> None:
        """Abort the current analysis"""
        self.is_analyzing = False

    def _run_analysis(
        self,
        video_value: bytes,
        json_value: bytes,
        video_filename: str,
        json_filename: str,
        show_info: bool,
        show_heatmap: bool,
        progress_callback: Callable[[int], None],
        status_callback: Callable[[str, str], None],
        download_widget,
    ) -> None:
        """Run the analysis in background thread"""
        try:
            video_stem = Path(video_filename).stem

            # Create temporary files for processing
            temp_video_path = self.project_root / f"temp_{video_filename}"
            temp_json_path = self.project_root / f"temp_{json_filename}"

            with open(temp_video_path, "wb") as f:
                f.write(video_value)

            with open(temp_json_path, "wb") as f:
                f.write(json_value)

            # Generate output filename - save to Downloads folder by default
            output_stem = video_stem + "_ethological_analysis"
            output_filename = f"{output_stem}{Path(video_filename).suffix}"

            # Save to temporary folder in ethological_tab
            output_path = self.temp_dir / output_filename

            progress_callback(10)
            status_callback(
                "**Status:** 🔄 Loading video and tracking data...\n\nPreparing files for processing...",
                "#fff3cd",
            )

            progress_callback(20)
            status_callback(
                "**Status:** 🔄 Creating visualizer...\n\nInitializing video processing engine...",
                "#fff3cd",
            )

            # Create visualizer
            visualizer = TrackingVisualizer(
                video_path=str(temp_video_path),
                json_path=str(temp_json_path),
                output_path=str(output_path),
                show_info=show_info,
                show_heatmap=show_heatmap,
                progress_callback=progress_callback,
            )

            progress_callback(30)
            status_callback(
                (
                    f"**Status:** 🔄 Processing video frames...\n\n"
                    f"Analyzing {visualizer.total_frames} frames with tracking data..."
                ),
                "#fff3cd",
            )

            # Process video - now with real progress updates from visualizer
            status_callback(
                f"**Status:** 🔄 Processing {visualizer.total_frames} frames...\n\nReal-time progress will be shown below...",
                "#fff3cd",
            )
            visualizer.process_video()

            if not self.is_analyzing:  # Check if aborted
                return

            # Cleanup
            visualizer.cleanup()

            progress_callback(100)

            # Small delay to ensure UI updates properly
            time.sleep(0.2)

            # Success
            file_size_mb = output_path.stat().st_size / 1024 / 1024
            success_msg = (
                "**Status:** ✅ **Analysis Complete**"
                f"**File:** {output_path.name} ({file_size_mb:.1f} MB)"
                "**Location:** Temporary folder (ethological_tab/temp)"
                f"**Options:** Info Panel: {'✅' if show_info else '❌'} | Heatmap: {'✅' if show_heatmap else '❌'}"
                "Video processing completed successfully. Download link ready below."
            )

            status_callback(success_msg, "#d4edda")

            # Store output path for download
            self.current_output_path = output_path
            
            # Configure FileDownload widget with the video file
            self._configure_download(output_path, download_widget)

        except ImportError as e:
            error_msg = (
                "**Status:** ❌ **Import Error**"
                f"Cannot import TrackingVisualizer: {str(e)}"
                "Make sure testVideo_json.py is in the ethological_tab directory."
            )
            status_callback(error_msg, "#f8d7da")

        except Exception as e:
            error_msg = (
                "**Status:** ❌ **Analysis Failed**"
                f"Error: {str(e)}"
                "Please check that the video and JSON files are valid."
            )
            status_callback(error_msg, "#f8d7da")

        finally:
            # Cleanup temp files
            for temp_file in ["temp_video_path", "temp_json_path"]:
                if temp_file in locals() and locals()[temp_file].exists():
                    try:
                        locals()[temp_file].unlink()
                    except:
                        pass


    def _configure_download(self, output_path: Path, download_widget) -> None:
        """Configure FileDownload widget with the generated video file"""
        try:
            if not output_path.exists():
                return
                
            
            # Read the video file
            with open(output_path, "rb") as f:
                video_data = f.read()
            
            # Create BytesIO object
            file_obj = BytesIO(video_data)
            file_obj.seek(0)
            
            # Configure FileDownload widget
            download_widget.file = file_obj
            download_widget.filename = output_path.name
            download_widget.mime_type = "video/mp4"
            download_widget.disabled = False
            download_widget.visible = True
            
        except Exception as e:
            print(f"Error configuring download: {e}")
