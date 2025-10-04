"""Open Field Analysis - Circular arena for anxiety behavior analysis"""
import json
import math
import os
from io import BytesIO
from pathlib import Path

import cv2 as cv
import numpy as np
import panel as pn
from bokeh.events import Pan, PanEnd, PanStart
from bokeh.models import Range1d
from bokeh.plotting import figure
from PIL import Image
from ultralytics import YOLO

# Try to import with GPU support, fallback to CPU
try:
    from torch import cuda
    from torch.backends import mps

    GPU_AVAILABLE = True
except ImportError:
    class MockCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class MockMps:
        @staticmethod
        def is_available() -> bool:
            return False

    cuda = MockCuda()
    mps = MockMps()
    GPU_AVAILABLE = False


class OpenFieldTab:
    def __init__(self, project_root: Path, temp_dir: Path) -> None:
        self.project_root = project_root
        self.temp_dir = temp_dir
        self.pose_models_dir = Path(__file__).parent / "pose"

        # Video and model
        self.video_loaded = False
        self.yolo_model = None
        self.tmp_file = None
        self.background = None
        self.current_frame = np.ones((640, 640), dtype=np.uint8) * 240

        # ROIs - 3 concentric circles (central area, intermediate border, outer border)
        # Dictionary mapping label to ROI data: {label: {center_x, center_y, radius, renderer}}
        self.roi_circles = {}
        self.roi_renderers = {}  # Map label to renderer for display

        # Drawing state
        self.drawing_circle = False
        self.circle_start_point = {"x": 0, "y": 0}
        self.circle_temp_annotation = None

        # Moving ROI state
        self.moving_roi = False
        self.moving_roi_index = None
        self.moving_roi_renderer = None
        self.moving_roi_offset = {"x": 0, "y": 0}  # Offset from center to click point

        # Tracking state
        self.tracking_active = False
        self.tracking_data = []
        self.frame_count = 0
        self.total_frames = 0
        self.video_capture = None
        self.tracking_callback = None

        # Device
        if GPU_AVAILABLE and cuda.is_available():
            self.device = "cuda"
            print("🚀 GPU (CUDA) available - using GPU acceleration")
        elif GPU_AVAILABLE and mps.is_available():
            self.device = "mps"
            print("🚀 MPS (Apple Silicon) available - using MPS acceleration")
        else:
            self.device = "cpu"
            print("💻 Running in CPU-only mode")

        # Create UI components
        self._create_ui()

    def _create_ui(self) -> None:
        """Create UI components"""
        # File input
        self.video_input = pn.widgets.FileInput(
            name="Upload Video",
            accept=".mp4,.avi,.mov,.mkv",
            multiple=False,
            width=400,
        )

        # Model selection
        self.model_select = pn.widgets.Select(
            name="YOLO Pose Model",
            options=self._get_pose_models(),
            width=400,
        )

        # ROI type (simplified - only circles)
        self.roi_label_select = pn.widgets.Select(
            name="ROI Label",
            options=["Central Area", "Intermediate Border", "Outer Border"],
            width=200,
        )

        # Buttons
        self.button_delete_current = pn.widgets.Button(
            name="❌ Delete Current",
            button_type="danger",
            width=140,
            disabled=True,
        )

        self.button_clear_rois = pn.widgets.Button(
            name="🗑 Clear All",
            button_type="warning",
            width=140,
            disabled=True,
        )

        self.button_start_analysis = pn.widgets.Button(
            name="▶ Start Analysis",
            button_type="success",
            width=140,
            disabled=True,
        )

        self.button_stop_analysis = pn.widgets.Button(
            name="⏹ Stop",
            button_type="danger",
            width=140,
            disabled=True,
        )

        self.button_download = pn.widgets.FileDownload(
            label="📥 Download Data",
            button_type="primary",
            width=140,
            disabled=True,
            visible=True,
            auto=False,
        )

        # Progress bar
        self.progress_bar = pn.indicators.Progress(
            name="Progress",
            value=0,
            max=100,
            visible=False,
            width=400,
        )

        # Status panel
        self.status = pn.pane.Markdown(
            "**Status:** Ready\n\nUpload a video to start.",
            styles={"background": "#f8f9fa", "padding": "15px", "border-radius": "5px"},
            width=400,
            min_height=150,
        )

        # Frame display
        self.frame_pane = figure(
            width=640,
            height=640,
            tools="reset",
            x_range=(0, 640),
            y_range=(0, 640),
            match_aspect=True,  # Maintain aspect ratio
        )
        self.frame_pane.margin = 0
        self.frame_pane.border_fill_color = "#808080"
        self.frame_pane.xaxis.visible = False
        self.frame_pane.yaxis.visible = False
        self.frame_pane.grid.visible = False
        self.frame_pane.toolbar_location = None

        # Initial gray image - will be replaced when video is loaded
        # No need to create initial image, it will be created in _display_frame
        self.current_frame_render = None

        # Store video dimensions - will be updated when video is loaded
        self.video_width = 640
        self.video_height = 640

        # Connect events
        self.video_input.param.watch(self._on_video_upload, "value")
        self.roi_label_select.param.watch(self._on_label_change, "value")
        self.frame_pane.on_event(PanStart, self._on_pan_start)
        self.frame_pane.on_event(Pan, self._on_pan)
        self.frame_pane.on_event(PanEnd, self._on_pan_end)
        self.button_delete_current.on_click(self._delete_current_roi)
        self.button_clear_rois.on_click(self._clear_rois)
        self.button_start_analysis.on_click(self._start_analysis)
        self.button_stop_analysis.on_click(self._stop_analysis)
        # FileDownload widget doesn't need on_click - it handles download automatically

    def _get_pose_models(self) -> list[str]:
        """Get list of available pose models"""
        if not self.pose_models_dir.exists():
            return ["No models found"]

        models = [f.name for f in self.pose_models_dir.glob("*.pt") if "pose" in f.name.lower()]
        return models if models else ["No pose models found"]

    def _on_label_change(self, event) -> None:
        """Handle ROI label selection change"""
        current_label = event.new
        # Enable delete button only if current label has a ROI
        self.button_delete_current.disabled = current_label not in self.roi_circles

    def _on_video_upload(self, event) -> None:
        """Handle video upload"""
        if not event.new:
            return

        try:
            # Save video to temp file
            video_format = self.video_input.mime_type
            mime_to_ext = {"video/mp4": ".mp4", "video/avi": ".avi"}
            ext = mime_to_ext.get(video_format, ".mp4")

            self.tmp_file = self.temp_dir / f"open_field_video{ext}"
            with open(self.tmp_file, "wb") as f:
                f.write(event.new)

            # Calculate background (average of sampled frames to remove animal)
            self._calculate_background()
            self.video_loaded = True
            self.button_start_analysis.disabled = False

            self._update_status(
                f"**Status:** ✅ Video loaded\n\n"
                f"**Frames:** {self.total_frames}\n\n"
                f"Draw circular ROIs on the arena.",
                "#d1ecf1"
            )

        except Exception as e:
            self._update_status(f"**Status:** ❌ Error loading video\n\n{str(e)}", "#f8d7da")

    def _calculate_background(self) -> None:
        """Calculate background by averaging sampled frames (removes animal from scene)"""
        try:
            cap = cv.VideoCapture(str(self.tmp_file))
            total_frames = int(cap.get(cv.CAP_PROP_FRAME_COUNT))
            self.total_frames = total_frames

            if not cap.isOpened():
                self._update_status("**Status:** ❌ Video couldn't be loaded", "#f8d7da")
                return

            # Read first frame to get dimensions and initialize accumulator
            ret, sample_frame = cap.read()
            if not ret:
                self._update_status("**Status:** ❌ Couldn't read video frames", "#f8d7da")
                cap.release()
                return

            # Get video dimensions
            height, width = sample_frame.shape[:2]
            self.video_width = width
            self.video_height = height

            # Update frame pane dimensions BEFORE displaying anything
            self.frame_pane.width = width
            self.frame_pane.height = height
            self.frame_pane.x_range = Range1d(0, width)
            self.frame_pane.y_range = Range1d(0, height)

            # Show progress bar
            self.progress_bar.visible = True
            self.progress_bar.value = 0
            self.progress_bar.max = 100

            # Reset video position
            cap.set(cv.CAP_PROP_POS_FRAMES, 0)

            # Initialize frame accumulator
            frame_count = 0
            median_accumulator = np.zeros_like(sample_frame, dtype=np.float32)

            # Sample frames to calculate background (process ~200 frames for efficiency)
            total_samples = min(200, total_frames)
            frame_step = max(1, total_frames // total_samples)

            current_frame = 0

            while current_frame < total_frames:
                # Set position to the current frame
                cap.set(cv.CAP_PROP_POS_FRAMES, current_frame)
                ret, frame = cap.read()

                if not ret:
                    break

                # Convert to float and accumulate
                frame_float = frame.astype(np.float32)
                median_accumulator += frame_float
                frame_count += 1

                # Update progress bar
                self.progress_bar.name = f"Calculating background... ({current_frame}/{total_frames})"
                self.progress_bar.value = int(current_frame / total_frames * 100)

                # Move to next frame to sample
                current_frame += frame_step

            # Hide progress bar
            self.progress_bar.visible = False
            self.progress_bar.name = "Progress"
            cap.release()

            if frame_count == 0:
                self._update_status("**Status:** ❌ No frames were processed", "#f8d7da")
                return

            # Calculate the average (approximating median for efficiency)
            self.background = (median_accumulator / frame_count).astype(np.uint8)

            # Display background
            self._display_frame(self.background)

            print(f"✅ Background calculated from {frame_count} sampled frames")

        except Exception as e:
            self.progress_bar.visible = False
            print(f"Background calculation error: {e}")
            self._update_status(f"**Status:** ❌ Background calculation error\n\n{str(e)}", "#f8d7da")

    def _display_frame(self, frame: np.ndarray) -> None:
        """Display frame in bokeh pane"""
        # Convert BGR to RGB
        img = Image.fromarray(cv.cvtColor(frame, cv.COLOR_BGR2RGB))

        # Flip and convert to RGBA
        img_array = np.array(img.transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA"))
        imview = img_array.view(np.uint32).reshape(img_array.shape[:2])

        height, width = frame.shape[:2]

        # Update existing image or create new one
        if (self.current_frame_render is not None and
            hasattr(self, 'current_frame_render') and
            self.current_frame_render in self.frame_pane.renderers):
            # Update existing image data
            self.current_frame_render.data_source.data["image"] = [imview]
        else:
            # Remove any existing images first
            renderers_to_keep = [r for r in self.frame_pane.renderers
                                if "ImageRGBA" not in str(type(r))]
            self.frame_pane.renderers = renderers_to_keep

            # Create new image with correct dimensions
            self.current_frame_render = self.frame_pane.image_rgba(
                image=[imview], x=0, y=0, dw=width, dh=height
            )

    def _on_pan_start(self, event) -> None:
        """Start drawing circle ROI or moving existing ROI"""
        if not self.video_loaded:
            return

        # Get current label
        current_label = self.roi_label_select.value

        # Check if click is near the center of the current label's ROI (within 30 pixels)
        click_tolerance = 30
        if current_label in self.roi_circles:
            roi = self.roi_circles[current_label]
            dist_to_center = math.sqrt((event.x - roi["center_x"]) ** 2 + (event.y - roi["center_y"]) ** 2)

            if dist_to_center <= click_tolerance:
                # Start moving this ROI
                self.moving_roi = True
                self.moving_roi_index = current_label  # Store label instead of index
                self.moving_roi_offset = {
                    "x": event.x - roi["center_x"],
                    "y": event.y - roi["center_y"]
                }

                # Get the renderer for this ROI
                self.moving_roi_renderer = self.roi_renderers.get(current_label)

                print(f"📍 Moving ROI: {current_label}")
                return

        # No ROI clicked - start drawing new circle (will replace existing for this label)
        self.drawing_circle = True
        self.circle_start_point = {"x": event.x, "y": event.y}

        # Create temporary circle
        angles = np.linspace(0, 2 * np.pi, 50)
        circle_x = [event.x + 5 * np.cos(angle) for angle in angles]
        circle_y = [event.y + 5 * np.sin(angle) for angle in angles]

        self.circle_temp_annotation = self.frame_pane.line(
            circle_x, circle_y,
            line_color="blue",
            line_width=2,
            line_dash="dashed",
            line_alpha=0.8,
        )

    def _on_pan(self, event) -> None:
        """Update circle while dragging (drawing new or moving existing)"""
        # Moving existing ROI
        if self.moving_roi and self.moving_roi_renderer and self.moving_roi_index is not None:
            label = self.moving_roi_index  # Now stores label
            roi = self.roi_circles[label]

            # Calculate new center (accounting for click offset)
            new_center_x = event.x - self.moving_roi_offset["x"]
            new_center_y = event.y - self.moving_roi_offset["y"]

            # Update circle position
            angles = np.linspace(0, 2 * np.pi, 50)
            circle_x = [new_center_x + roi["radius"] * np.cos(angle) for angle in angles]
            circle_y = [new_center_y + roi["radius"] * np.sin(angle) for angle in angles]

            self.moving_roi_renderer.data_source.data = {"x": circle_x, "y": circle_y}
            return

        # Drawing new circle
        if not self.drawing_circle or not self.circle_temp_annotation:
            return

        center_x = self.circle_start_point["x"]
        center_y = self.circle_start_point["y"]
        radius = math.sqrt((event.x - center_x) ** 2 + (event.y - center_y) ** 2)

        angles = np.linspace(0, 2 * np.pi, 50)
        circle_x = [center_x + radius * np.cos(angle) for angle in angles]
        circle_y = [center_y + radius * np.sin(angle) for angle in angles]

        self.circle_temp_annotation.data_source.data = {"x": circle_x, "y": circle_y}

    def _on_pan_end(self, event) -> None:
        """Finalize circle ROI (drawing new or moving existing)"""
        # Finalize moving existing ROI
        if self.moving_roi and self.moving_roi_index is not None:
            label = self.moving_roi_index  # Now stores label
            roi = self.roi_circles[label]

            # Calculate new center (accounting for click offset)
            new_center_x = event.x - self.moving_roi_offset["x"]
            new_center_y = event.y - self.moving_roi_offset["y"]

            # Update ROI data with new position
            roi["center_x"] = new_center_x
            roi["center_y"] = new_center_y

            print(f"✅ ROI moved: {label} to ({new_center_x:.1f}, {new_center_y:.1f})")

            # Reset moving state
            self.moving_roi = False
            self.moving_roi_index = None
            self.moving_roi_renderer = None
            self.moving_roi_offset = {"x": 0, "y": 0}
            return

        # Finalize drawing new circle
        if not self.drawing_circle:
            return

        # Remove temporary circle
        if self.circle_temp_annotation in self.frame_pane.renderers:
            self.frame_pane.renderers.remove(self.circle_temp_annotation)

        # Calculate final circle
        center_x = self.circle_start_point["x"]
        center_y = self.circle_start_point["y"]
        radius = math.sqrt((event.x - center_x) ** 2 + (event.y - center_y) ** 2)

        if radius < 10:  # Too small, ignore
            self.drawing_circle = False
            return

        # Color based on label
        label = self.roi_label_select.value
        colors = {
            "Central Area": "green",
            "Intermediate Border": "orange",
            "Outer Border": "red",
        }
        color = colors.get(label, "blue")

        # If ROI for this label already exists, remove the old renderer
        if label in self.roi_renderers:
            old_renderer = self.roi_renderers[label]
            if old_renderer in self.frame_pane.renderers:
                self.frame_pane.renderers.remove(old_renderer)
            print(f"🔄 Replacing existing ROI for {label}")

        # Draw final circle
        angles = np.linspace(0, 2 * np.pi, 50)
        circle_x = [center_x + radius * np.cos(angle) for angle in angles]
        circle_y = [center_y + radius * np.sin(angle) for angle in angles]

        circle_renderer = self.frame_pane.line(
            circle_x, circle_y,
            line_color=color,
            line_width=3,
            line_alpha=0.7,
        )

        # Store ROI data (replaces existing for this label)
        self.roi_circles[label] = {
            "center_x": center_x,
            "center_y": center_y,
            "radius": radius,
            "label": label,
            "color": color,
        }
        self.roi_renderers[label] = circle_renderer

        self.drawing_circle = False

        # Update button states
        self.button_delete_current.disabled = False
        self.button_clear_rois.disabled = len(self.roi_circles) == 0

        print(f"✅ ROI created: {label} (radius={radius:.1f}px)")

    def _delete_current_roi(self, event) -> None:
        """Delete the ROI for the currently selected label"""
        current_label = self.roi_label_select.value

        if current_label not in self.roi_circles:
            return

        # Remove renderer from display
        if current_label in self.roi_renderers:
            renderer = self.roi_renderers[current_label]
            if renderer in self.frame_pane.renderers:
                self.frame_pane.renderers.remove(renderer)
            del self.roi_renderers[current_label]

        # Remove ROI data
        del self.roi_circles[current_label]

        # Update button states
        self.button_delete_current.disabled = True
        self.button_clear_rois.disabled = len(self.roi_circles) == 0

        print(f"🗑 Deleted ROI: {current_label}")

        self._update_status(
            f"**Status:** 🗑 ROI deleted: {current_label}\n\n"
            f"Draw a new ROI for this label if needed.",
            "#f8f9fa"
        )

    def _clear_rois(self, event) -> None:
        """Clear all ROIs"""
        # Reset drawing state
        self.drawing_circle = False
        self.circle_temp_annotation = None

        # Reset moving state
        self.moving_roi = False
        self.moving_roi_index = None
        self.moving_roi_renderer = None
        self.moving_roi_offset = {"x": 0, "y": 0}

        # Remove all non-image renderers (circles, lines, etc.)
        renderers_to_keep = []
        for renderer in self.frame_pane.renderers:
            renderer_type = str(type(renderer))
            if "image" in renderer_type.lower() or "ImageRGBA" in renderer_type:
                renderers_to_keep.append(renderer)

        self.frame_pane.renderers = renderers_to_keep

        # Clear ROI data
        self.roi_circles = {}
        self.roi_renderers = {}
        self.button_clear_rois.disabled = True
        self.button_delete_current.disabled = True

        # Redisplay background to ensure it's visible
        if self.background is not None:
            self._display_frame(self.background)

        self._update_status(
            f"**Status:** 🗑 ROIs cleared\n\n"
            f"Draw new ROIs on the video.",
            "#f8f9fa"
        )

        print("🗑 ROIs cleared")

    def _start_analysis(self, event) -> None:
        """Start pose estimation analysis"""
        if not self.video_loaded:
            return

        # Load YOLO pose model
        if not self.yolo_model:
            model_name = self.model_select.value
            if "No" in model_name:
                self._update_status("**Status:** ❌ No valid pose model selected", "#f8d7da")
                return

            model_path = self.pose_models_dir / model_name
            try:
                self.yolo_model = YOLO(str(model_path))
                if self.device == "cuda":
                    self.yolo_model.to("cuda")
                print(f"✅ Pose model loaded: {model_name}")
            except Exception as e:
                self._update_status(f"**Status:** ❌ Error loading model\n\n{str(e)}", "#f8d7da")
                return

        # Start processing
        self.tracking_active = True
        self.tracking_data = []
        self.frame_count = 0
        self.button_start_analysis.disabled = True
        self.button_stop_analysis.disabled = False
        self.progress_bar.visible = True
        self.progress_bar.max = self.total_frames
        self.progress_bar.value = 0

        self._update_status("**Status:** 🔄 Processing...", "#fff3cd")

        # Open video capture
        self.video_capture = cv.VideoCapture(str(self.tmp_file))

        # Start periodic callback for real-time processing
        self.tracking_callback = pn.state.add_periodic_callback(
            self._process_frame, 33  # ~30 FPS
        )

        print("▶ Started real-time pose estimation")

    def _process_frame(self) -> None:
        """Process single frame with YOLO pose estimation (real-time)"""
        if not self.tracking_active or not self.video_capture:
            return

        # Check if finished
        if self.frame_count >= self.total_frames:
            self._finish_analysis()
            return

        # Read frame
        ret, frame = self.video_capture.read()
        if not ret:
            self._finish_analysis()
            return

        # Run YOLO pose estimation
        results = self.yolo_model(frame, verbose=False)

        # Extract keypoints
        frame_data = {
            "frame": self.frame_count,
            "keypoints": [],
            "roi_location": None,
        }

        keypoints_array = None
        if results[0].keypoints is not None:
            keypoints = results[0].keypoints.xy.cpu().numpy()

            # Debug: print keypoints shape
            if self.frame_count == 0:
                print(f"🔍 Keypoints shape: {keypoints.shape}")
                print(f"🔍 Number of detections: {len(keypoints)}")
                if len(keypoints) > 0:
                    print(f"🔍 Keypoints per detection: {keypoints[0].shape}")

            if len(keypoints) > 0:
                # Get first detection (first animal)
                keypoints_array = keypoints[0]

                # Ensure we have exactly 7 keypoints
                if len(keypoints_array) > 7:
                    print(f"⚠️  Warning: Got {len(keypoints_array)} keypoints, expected 7. Trimming.")
                    keypoints_array = keypoints_array[:7]

                frame_data["keypoints"] = keypoints_array.tolist()

                # Calculate centroid from HEAD keypoints only (N, LEar, REar, BC)
                # These are the first 4 keypoints: indices 0-3
                head_keypoints = keypoints_array[:4]
                kp_array = np.array(head_keypoints)
                valid_kps = kp_array[~np.isnan(kp_array).any(axis=1)]
                if len(valid_kps) > 0:
                    centroid_x = np.mean(valid_kps[:, 0])
                    centroid_y = np.mean(valid_kps[:, 1])

                    # Determine which ROI the head centroid is in
                    roi_location = self._get_roi_location(centroid_x, centroid_y)
                    frame_data["roi_location"] = roi_location

        # Calculate centroid for visualization (using HEAD keypoints only)
        centroid = None
        if keypoints_array is not None:
            # Use first 4 keypoints: N, LEar, REar, BC (head region)
            head_keypoints = keypoints_array[:4]
            kp_array = np.array(head_keypoints)
            valid_kps = kp_array[~np.isnan(kp_array).any(axis=1)]
            if len(valid_kps) > 0:
                centroid_x = np.mean(valid_kps[:, 0])
                centroid_y = np.mean(valid_kps[:, 1])
                centroid = (int(centroid_x), int(centroid_y))

        # Draw keypoints on frame
        frame_with_keypoints = self._draw_keypoints(frame, keypoints_array)

        # Draw centroid
        if centroid:
            cv.circle(frame_with_keypoints, centroid, 4, (255, 0, 255), -1)  # Magenta (smaller)
            cv.circle(frame_with_keypoints, centroid, 6, (255, 255, 255), 1)  # White border (thinner)

        # Display frame (without ROIs drawn - they are already in bokeh)
        self._display_frame(frame_with_keypoints)

        # Store data
        self.tracking_data.append(frame_data)
        self.frame_count += 1
        self.progress_bar.value = self.frame_count

        # Update progress and status
        progress_pct = (self.frame_count / self.total_frames * 100) if self.total_frames > 0 else 0
        self.progress_bar.name = f"Processing: {self.frame_count}/{self.total_frames} ({progress_pct:.1f}%)"

        # Update status with frame and location info
        roi_loc = frame_data.get("roi_location", "Unknown")
        roi_colors = {
            "Central Area": "#d4edda",
            "Intermediate Border": "#fff3cd",
            "Outer Border": "#f8d7da",
            "Outside": "#e2e3e5",
        }
        status_color = roi_colors.get(roi_loc, "#f8f9fa")

        self._update_status(
            f"**Status:** 🔄 Processing\n\n"
            f"**Frame:** {self.frame_count}/{self.total_frames}\n\n"
            f"**Location:** {roi_loc}",
            status_color
        )

    def _draw_keypoints(self, frame: np.ndarray, keypoints: np.ndarray) -> np.ndarray:
        """Draw pose estimation keypoints on frame"""
        if keypoints is None or len(keypoints) == 0:
            return frame

        frame_draw = frame.copy()

        # Debug: show number of keypoints
        if self.frame_count == 0:
            print(f"🎨 Drawing {len(keypoints)} keypoints")

        # 7-keypoint mouse/rat model structure:
        #       N (0)
        #      /   \
        #  LEar(1) REar(2)
        #      \   /
        #      BC (3)
        #        |
        #      TB (4)
        #        |
        #      TM (5)
        #        |
        #      TT (6)

        colors = [
            (0, 0, 255),      # 0: N (Nose) - red
            (0, 255, 0),      # 1: LEar (Left Ear) - green
            (255, 0, 0),      # 2: REar (Right Ear) - blue
            (0, 255, 255),    # 3: BC (Body Center) - yellow
            (255, 0, 255),    # 4: TB (Tail Base) - magenta
            (0, 165, 255),    # 5: TM (Tail Middle) - orange
            (255, 255, 0),    # 6: TT (Tail Tip) - cyan
        ]

        # Draw keypoints (without labels)
        for idx, (x, y) in enumerate(keypoints):
            if not np.isnan(x) and not np.isnan(y):
                x, y = int(x), int(y)
                color = colors[idx % len(colors)]

                # Draw keypoint (smaller)
                cv.circle(frame_draw, (x, y), 3, color, -1)
                cv.circle(frame_draw, (x, y), 4, (255, 255, 255), 1)

        # Draw skeleton connections based on diagram
        # N (0) - LEar (1) - REar (2) - BC (3) - TB (4) - TM (5) - TT (6)
        connections = [
            (0, 1),   # N to LEar
            (0, 2),   # N to REar
            (1, 3),   # LEar to BC
            (2, 3),   # REar to BC
            (3, 4),   # BC to TB
            (4, 5),   # TB to TM
            (5, 6),   # TM to TT
        ]

        for p1, p2 in connections:
            if p1 < len(keypoints) and p2 < len(keypoints):
                x1, y1 = keypoints[p1]
                x2, y2 = keypoints[p2]
                if not (np.isnan(x1) or np.isnan(y1) or np.isnan(x2) or np.isnan(y2)):
                    cv.line(frame_draw, (int(x1), int(y1)), (int(x2), int(y2)),
                           (0, 255, 0), 1)

        return frame_draw

    def _finish_analysis(self) -> None:
        """Finish analysis and cleanup"""
        # Stop callback
        if self.tracking_callback:
            self.tracking_callback.stop()
            self.tracking_callback = None

        # Release video capture
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None

        # Update UI
        self.tracking_active = False
        self.button_start_analysis.disabled = False
        self.button_stop_analysis.disabled = True
        self.progress_bar.visible = False
        self.progress_bar.name = "Progress"

        # Automatically prepare download
        if len(self.tracking_data) > 0:
            self._prepare_download()

        self._update_status(
            f"**Status:** ✅ Analysis complete\n\n"
            f"**Frames processed:** {len(self.tracking_data)}\n\n"
            f"Click 'Download Data' to get results.",
            "#d4edda"
        )

        print(f"✅ Analysis complete: {len(self.tracking_data)} frames processed")

    def _get_roi_location(self, x: float, y: float) -> str:
        """Determine which ROI a point belongs to"""
        # Sort ROIs by radius (smallest first = central area)
        rois_list = list(self.roi_circles.values())
        sorted_rois = sorted(rois_list, key=lambda r: r["radius"])

        for roi in sorted_rois:
            dist = math.sqrt((x - roi["center_x"]) ** 2 + (y - roi["center_y"]) ** 2)
            if dist <= roi["radius"]:
                return roi["label"]

        return "Outside"

    def _stop_analysis(self, event) -> None:
        """Stop analysis"""
        self.tracking_active = False

        # Stop callback
        if self.tracking_callback:
            self.tracking_callback.stop()
            self.tracking_callback = None

        # Release video capture
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None

        # Update UI
        self.button_start_analysis.disabled = False
        self.button_stop_analysis.disabled = True
        self.progress_bar.visible = False
        self.progress_bar.name = "Progress"

        # Prepare download if we have data
        if len(self.tracking_data) > 0:
            self._prepare_download()

        self._update_status(
            f"**Status:** ⏹ Analysis stopped\n\n"
            f"**Frames processed:** {len(self.tracking_data)}",
            "#f8d7da"
        )

        print(f"⏹ Analysis stopped at frame {self.frame_count}")

    def _prepare_download(self) -> None:
        """Prepare analysis data for download"""
        if not self.tracking_data:
            return

        try:
            output_data = {
                "metadata": {
                    "total_frames": len(self.tracking_data),
                    "video_file": self.video_input.filename if hasattr(self.video_input, "filename") else "unknown",
                    "model": self.model_select.value,
                    "device": self.device,
                    "keypoint_names": ["N", "LEar", "REar", "BC", "TB", "TM", "TT"],
                    "keypoint_descriptions": {
                        "N": "Nose",
                        "LEar": "Left Ear",
                        "REar": "Right Ear",
                        "BC": "Body Center",
                        "TB": "Tail Base",
                        "TM": "Tail Middle",
                        "TT": "Tail Tip"
                    },
                    "roi_detection_method": "head_centroid",
                    "roi_detection_keypoints": "First 4 keypoints (N, LEar, REar, BC) used to determine ROI location"
                },
                "rois": self.roi_circles,
                "tracking_data": self.tracking_data,
            }

            # Convert to JSON string
            json_str = json.dumps(output_data, indent=2)

            # Create BytesIO object
            file_obj = BytesIO(json_str.encode('utf-8'))
            file_obj.seek(0)

            # Generate filename
            video_name = self.video_input.filename if hasattr(self.video_input, "filename") else "video"
            video_name_base = video_name.rsplit('.', 1)[0] if '.' in video_name else video_name
            filename = f"{video_name_base}_open_field_analysis.json"

            # Configure FileDownload widget
            self.button_download.file = file_obj
            self.button_download.filename = filename
            self.button_download.mime_type = "application/json"
            self.button_download.disabled = False

            print(f"✅ Download prepared: {filename}")

        except Exception as e:
            print(f"Error preparing download: {e}")
            self._update_status(
                f"**Status:** ❌ Error preparing download\n\n{str(e)}",
                "#f8d7da"
            )

    def _update_status(self, message: str, color: str) -> None:
        """Update status panel"""
        self.status.object = message
        self.status.styles = {
            "background": color,
            "padding": "15px",
            "border-radius": "5px",
        }

    def get_panel(self) -> pn.Column:
        """Return the panel layout"""
        return pn.Column(
            pn.pane.Markdown("### 🔵 Open Field - Circular Arena Analysis"),
            pn.Spacer(height=15),
            pn.Row(
                pn.Column(
                    pn.pane.Markdown("**Configuration:**", margin=(0, 0, 10, 0)),
                    self.video_input,
                    self.model_select,
                    pn.Spacer(height=10),
                    pn.pane.Markdown("**Draw ROIs:**", margin=(0, 0, 5, 0)),
                    self.roi_label_select,
                    pn.pane.Markdown(
                        "*Drag on the video to create circular ROIs*",
                        styles={"font-size": "11px", "color": "#666"},
                    ),
                    pn.Spacer(height=15),
                    pn.pane.Markdown("**ROI Controls:**", margin=(0, 0, 10, 0)),
                    pn.Row(
                        self.button_delete_current,
                        pn.Spacer(width=10),
                        self.button_clear_rois,
                    ),
                    pn.Spacer(height=15),
                    pn.pane.Markdown("**Analysis Controls:**", margin=(0, 0, 10, 0)),
                    pn.Row(
                        pn.Column(
                            self.button_start_analysis,
                            self.button_download,
                        ),
                        pn.Spacer(width=10),
                        self.button_stop_analysis,
                    ),
                    pn.Spacer(height=15),
                    self.status,
                    styles={
                        "background": "#f0f8ff",
                        "padding": "20px",
                        "border-radius": "8px",
                    },
                    width=450,
                ),
                pn.Spacer(width=20),
                pn.Column(
                    self.progress_bar,
                    self.frame_pane,
                ),
            ),
        )
