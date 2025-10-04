from io import BytesIO

import cv2 as cv
import numpy as np
import panel as pn
from bokeh.events import Pan, PanEnd, PanStart, Tap
from bokeh.models import BoxAnnotation, PolyAnnotation, Range1d
from bokeh.plotting import figure
from PIL import Image

# Try to import with GPU support, fallback to CPU
try:
    from torch import cuda
    from torch.backends import mps

    GPU_AVAILABLE = True
except ImportError:
    # Mock for CPU-only mode
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

import math
import os
from threading import Timer

from ultralytics import YOLO

from .export_json import create_download_filename, export_tracking_data, convert_rois_to_dict
from .processing.tracking import create_roi_mask, draw_rois, process_frame

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
YOLO_RESOLUTION = (640, 640)
ROI_TYPES = ["Rectangle", "Polygon", "Circle"]

pn.extension()


class TrackingTab:
    def __init__(self) -> None:
        # select
        self.select_model_name = None
        self.select_experiment_type = None

        # list of models
        self.models_name = ["Default.pt"]

        # slider
        self.slider_confidence = None
        self.slider_iou = None

        # file input
        self.file_input = None

        # yolo model
        self.yolo_model = None

        # buttons
        self.button_start_tracking = None
        self.button_pause_tracking = None
        self.button_stop_tracking = None
        self.button_clear_roi = None

        # tracking state
        self.tracking_paused = False
        self.button_save_roi_json = None
        self.button_download_json = None

        # frames
        self.current_frame = np.ones(YOLO_RESOLUTION, dtype=np.uint8) * 240
        # cv.putText(self.current_frame, "No video available yet!", (240, 200), cv.FONT_HERSHEY_COMPLEX_SMALL, 1, (0,0,0), 1)

        # store rois
        self.rois = []
        self.select_roi = None
        self.roi_in_track = None

        # roi bounding box
        self.bounding_box = BoxAnnotation(fill_alpha=0.3, fill_color="red")
        self.start_bounding_box = {"x": 0, "y": 0}

        # roi polygon annotation
        self.poly_annotation_points_draw = []  # store dot drawing
        self.poly_annotation_points_x = []  # store x-coordinates
        self.poly_annotation_points_y = []  # store y-coordinates

        # roi circle
        self.circle_annotation_points_draw = []
        self.circle_annotation_points = []
        self.circle_x_y_points = []
        self.circle_temp_annotation = None
        self.circle_start_point = {"x": 0, "y": 0}

        # polygon lines (for visual feedback)
        self.poly_lines = []

        # video
        self.video_loaded = False
        self.background = None
        self.background_frame = None  # Grayscale background for template matching

        # tracking
        self.callback_tracking = None

        # Storage for circle ROI data (since we can't add attributes to GlyphRenderer)
        self.circle_roi_data = (
            {}
        )  # Dict to store {roi_id: {center_x, center_y, radius}}

        self.tracking_log = pn.pane.Markdown("", visible=False)
        self.log_messages = []  # Store all log messages
        self.tracking_data = []
        self.frame_count = 0
        self.total_frames = 0  # Total frames in the video
        self.no_detection_count = 0
        self.yolo_detections = 0
        self.template_detections = 0
        self.mask = None

        # progress bar
        self.progress_bar = pn.indicators.Progress(
            name="Progress", value=0, max=100, visible=False, width=620
        )

        # warning
        self.warning = pn.pane.Alert(
            "## Alert\n", alert_type="danger", visible=False, width=620
        )

        # device
        self.device = None

        # cleanup session
        pn.state.on_session_destroyed(self._cleanup_session)

        # create temp directory if it doesn't exist
        self._ensure_temp_dir()

        # tab settings
        self._settings()

    def _ensure_temp_dir(self) -> None:
        """Create temp directory if it doesn't exist"""
        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)

    def _settings(self) -> None:
        # selects
        self._yolo_models_select()
        self._experiment_type()
        self._select_roi()

        # sliders
        self._confidence_threshold()
        self._iou_threshold()

        # file input
        self._file_input()

        # buttons
        self._buttons()

        # frame display
        self.frame_pane = figure(
            width=640, height=640, tools="reset", x_range=(0, 640), y_range=(0, 640)
        )
        self.frame_pane.margin = 0
        self.frame_pane.border_fill_color = "#808080"
        self.frame_pane.outline_line_color = None
        self.frame_pane.outline_line_width = 1

        # layout of figure tool bar
        self.frame_pane.xaxis.visible = False
        self.frame_pane.yaxis.visible = False
        self.frame_pane.grid.visible = False
        self.frame_pane.toolbar_location = None

        # initial image (gray)
        img = Image.fromarray(self.current_frame)

        # bokeh format
        img_array = np.array(img.transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA"))
        self.imview = img_array.view(np.uint32).reshape(img_array.shape[:2])

        self.current_frame = self.frame_pane.image_rgba(
            image=[self.imview], x=0, y=0, dw=640, dh=640
        )
        self.frame_view = None

        # checking device with GPU fallback
        if GPU_AVAILABLE and cuda.is_available():
            self.device = "cuda"
            print("🚀 GPU (CUDA) available - using GPU acceleration")
        elif GPU_AVAILABLE and mps.is_available():
            self.device = "mps"
            print("🚀 MPS (Apple Silicon) available - using MPS acceleration")
        else:
            self.device = "cpu"
            if GPU_AVAILABLE:
                print("⚠️  GPU not available - falling back to CPU")
            else:
                print("💻 Running in CPU-only mode")

        # connect functions
        self._connect_events()

    def _yolo_models_select(self) -> None:
        # Create models directory if it doesn't exist
        os.makedirs(MODELS_DIR, exist_ok=True)

        # Update models list from the models directory
        self._update_models_list()

        self.select_model_name = pn.widgets.Select(
            name="Select a YOLO Model", options=self.models_name, width=620
        )

    def _experiment_type(self) -> None:
        self.experiment_type = ["EPM", "OF_Rectangle", "OF_Circular_1", "OF_Circular_2"]

        self.select_experiment_type = pn.widgets.Select(
            name="Experiment Type", options=self.experiment_type
        )

    def _select_roi(self) -> None:
        self.select_roi = pn.widgets.Select(name="ROI Type", options=ROI_TYPES)

    def _confidence_threshold(self) -> None:
        self.slider_confidence = pn.widgets.FloatSlider(
            name="Confidence Threshold", start=0.10, end=0.9, step=0.01, value=0.25
        )

    def _iou_threshold(self) -> None:
        self.slider_iou = pn.widgets.FloatSlider(
            name="IOU Threshold", start=0.10, end=0.9, step=0.01, value=0.45
        )

    def _file_input(self) -> None:
        self.file_input = pn.widgets.FileInput(
            name="Upload video",
            accept=".mp4, .mov, .avi, .mkv",
            multiple=False,
            height=40,
            width=620,
        )

    def _buttons(self) -> None:

        self.button_start_tracking = pn.widgets.Button(
            name="▶ Start", button_type="success", width=80, height=35, disabled=True
        )

        self.button_pause_tracking = pn.widgets.Button(
            name="⏸ Pause", button_type="warning", width=80, height=35, disabled=True
        )

        self.button_stop_tracking = pn.widgets.Button(
            name="⏹ Stop", button_type="danger", width=80, height=35, disabled=True
        )

        self.button_clear_roi = pn.widgets.Button(
            name="🗑 Clear ROI",
            button_type="success",
            width=90,
            height=35,
            disabled=True,
        )

        self.button_save_roi_json = pn.widgets.FileDownload(
            button_type="primary",
            label="💾 Save ROI",
            width=90,
            height=35,
            disabled=True,
            auto=False,  # Don't auto-download, wait for user click
        )

        self.button_download_json = pn.widgets.FileDownload(
            label="📥 Download",
            button_type="success",
            width=100,
            height=35,
            disabled=True,
            auto=False,  # Don't auto-download, wait for user click
        )

    def _cleanup_temp_files(self) -> None:
        """Remove temporary files"""
        try:
            if hasattr(self, "tmp_file") and os.path.exists(self.tmp_file):
                os.remove(self.tmp_file)
                self._add_log_message("Temporary video file removed", "info")
        except Exception as e:
            self._add_log_message(f"Error removing temp files: {e}", "error")

    def _cleanup_session(self, session_context) -> None:
        # clear loop
        if self.callback_tracking is not None:
            self.callback_tracking.stop()
            self.callback_tracking = None

    def _thread_hide_warning(self) -> None:
        # hide warning
        self.hide_warning = Timer(3.0, self._hide_warning)
        self.hide_warning.start()

    def _connect_events(self) -> None:
        # load video
        self.file_input.param.watch(lambda event: self._load_video(event.new), "value")

        # roi box
        self.frame_pane.on_event(PanStart, self._bb_pan_start)
        self.frame_pane.on_event(Pan, self._bb_pan)
        self.frame_pane.on_event(PanEnd, self._bb_pan_end)
        self.frame_pane.on_event(Tap, self._poly_annotation)
        # Circle creation uses drag (pan events) only

        # buttons
        self.button_clear_roi.on_click(self._clear_roi)
        # self.button_save_roi_json.on_click(self._rois_to_json)
        self.button_start_tracking.on_click(self._start_tracking)
        print(f"✅ Start button callback registered: {self._start_tracking}")
        self.button_pause_tracking.on_click(self._pause_tracking)
        self.button_stop_tracking.on_click(self._stop_tracking)

    # ROI Functions
    def _bb_pan_start(self, event) -> None:
        if self.select_roi.value == "Rectangle":
            if not self.video_loaded:
                self.warning.object = "## Alert\n Video is not loaded!"
                self.warning.visible = True
                self._thread_hide_warning()
                return

            self.start_bounding_box["x"], self.start_bounding_box["y"] = (
                event.x,
                event.y,
            )

            # Create and add temporary bounding box for real-time feedback
            self.bounding_box = BoxAnnotation(
                fill_alpha=0.2,
                fill_color="blue",
                line_color="blue",
                line_width=2,
                line_dash="dashed",
            )
            self.bounding_box.left = self.bounding_box.right = event.x
            self.bounding_box.bottom = self.bounding_box.top = event.y
            
            # Add to frame pane for immediate visibility
            self.frame_pane.add_layout(self.bounding_box)

        elif self.select_roi.value == "Circle":
            if not self.video_loaded:
                self.warning.object = "## Alert\n Video is not loaded!"
                self.warning.visible = True
                self._thread_hide_warning()
                return

            self.circle_start_point["x"], self.circle_start_point["y"] = (
                event.x,
                event.y,
            )

            # Create temporary circle using line to draw circle outline
            import numpy as np

            angles = np.linspace(0, 2 * np.pi, 50)
            circle_x = [
                event.x + 5 * np.cos(angle) for angle in angles
            ]  # Start with radius 5
            circle_y = [event.y + 5 * np.sin(angle) for angle in angles]

            self.circle_temp_annotation = self.frame_pane.line(
                circle_x,
                circle_y,
                line_color="green",
                line_width=2,
                line_dash="dashed",
                line_alpha=0.8,
            )

    def _bb_pan(self, event) -> None:
        if self.video_loaded and self.select_roi.value == "Rectangle":
            self.bounding_box.left = min(self.start_bounding_box["x"], event.x)
            self.bounding_box.right = max(self.start_bounding_box["x"], event.x)
            self.bounding_box.top = min(self.start_bounding_box["y"], event.y)
            self.bounding_box.bottom = max(self.start_bounding_box["y"], event.y)

        elif self.video_loaded and self.select_roi.value == "Circle":
            # Calculate radius from start point to current position
            center_x = self.circle_start_point["x"]
            center_y = self.circle_start_point["y"]
            radius = math.sqrt((event.x - center_x) ** 2 + (event.y - center_y) ** 2)

            # Update temporary circle
            if self.circle_temp_annotation:
                import numpy as np

                angles = np.linspace(0, 2 * np.pi, 50)
                circle_x = [center_x + radius * np.cos(angle) for angle in angles]
                circle_y = [center_y + radius * np.sin(angle) for angle in angles]

                # Update the line data
                self.circle_temp_annotation.data_source.data = {
                    "x": circle_x,
                    "y": circle_y,
                }

    def _bb_pan_end(self, event) -> None:
        if self.video_loaded and self.select_roi.value == "Rectangle":
            # Remove temporary bounding box
            if self.bounding_box in self.frame_pane.renderers:
                self.frame_pane.renderers.remove(self.bounding_box)

            # Create final ROI box
            aux_box = BoxAnnotation(
                top_units="data",
                bottom_units="data",
                left_units="data",
                right_units="data",
                fill_alpha=0.3,
                fill_color="red",
                line_color="red",
                line_width=2,
                top=self.bounding_box.top,
                bottom=self.bounding_box.bottom,
                right=self.bounding_box.right,
                left=self.bounding_box.left,
            )
            self.rois.append(aux_box)

            self.frame_pane.add_layout(aux_box)

            self.button_clear_roi.disabled = False
            self.button_start_tracking.disabled = False
            self.button_save_roi_json.disabled = False

        elif self.video_loaded and self.select_roi.value == "Circle":
            # Remove temporary circle
            if self.circle_temp_annotation in self.frame_pane.renderers:
                self.frame_pane.renderers.remove(self.circle_temp_annotation)

            # Calculate final circle parameters
            center_x = self.circle_start_point["x"]
            center_y = self.circle_start_point["y"]
            radius = math.sqrt((event.x - center_x) ** 2 + (event.y - center_y) ** 2)

            # Create final circle using scatter (avoiding deprecation warning)
            size_value = radius * 2  # Bokeh scatter size is diameter
            final_circle = self.frame_pane.scatter(
                [center_x],
                [center_y],
                size=size_value,
                line_color="red",
                line_width=2,
                fill_alpha=0.3,
                fill_color="red",
                marker="circle",
            )

            # Store the actual circle data using the object ID as key
            circle_id = id(final_circle)  # Use Python object ID as unique identifier
            self.circle_roi_data[circle_id] = {
                "center_x": center_x,
                "center_y": center_y,
                "radius": radius,
            }

            self.rois.append(final_circle)


            self.button_clear_roi.disabled = False
            self.button_start_tracking.disabled = False
            self.button_save_roi_json.disabled = False

            # Force update the button state
            print(
                f"Enabling Start button. Current state: disabled={self.button_start_tracking.disabled}"
            )

            # Multiple attempts to force button enable
            try:
                # Method 1: Direct property set
                setattr(self.button_start_tracking, "disabled", False)

                # Method 2: Param trigger
                if hasattr(self.button_start_tracking, "param"):
                    self.button_start_tracking.param.trigger("disabled")

                # Method 3: Param watch trigger
                if hasattr(self.button_start_tracking, "param") and hasattr(
                    self.button_start_tracking.param, "watch"
                ):
                    self.button_start_tracking.param.disabled = False

                print(
                    f"After force update - button disabled: {self.button_start_tracking.disabled}"
                )
            except Exception as e:
                print(f"Error forcing button update: {e}")

            # Test if the button click works manually
            print(f"Testing button click manually...")
            try:
                # Trigger the button click event manually to test
                # self._start_tracking(None)  # Uncomment this line to test
                pass
            except Exception as e:
                print(f"Manual button test failed: {e}")

            print(
                f"Circle ROI created. Total ROIs: {len(self.rois)}"
            )
            print(
                f"video_loaded: {self.video_loaded}, button disabled: {self.button_start_tracking.disabled}"
            )
        
        self._rois_to_json()

    def _poly_annotation(self, event) -> None:
        if self.select_roi.value == "Polygon":
            if not self.video_loaded:
                self.warning.object = (
                    "## Alert\nOperation is invalid! Video is not loaded! "
                )
                self.warning.visible = True
                self._thread_hide_warning()
                return

            self.warning.visible = False
            self.button_clear_roi.disabled = False
            self.button_start_tracking.disabled = False
            self.button_save_roi_json.disabled = False

            # x and y coordinates (draw circle_dot)
            x = int(event.x)
            y = int(event.y)

            # store points to draw a polygon in the future
            self.poly_annotation_points_x.append(event.x)
            self.poly_annotation_points_y.append(event.y)
            size_poly = len(self.poly_annotation_points_x)

            begin_x, begin_y = (
                self.poly_annotation_points_x[0],
                self.poly_annotation_points_y[0],
            )
            last_x, last_y = (
                self.poly_annotation_points_x[size_poly - 1],
                self.poly_annotation_points_y[size_poly - 1],
            )

            distance = math.sqrt((last_x - begin_x) ** 2 + (last_y - begin_y) ** 2)

            # draw a polygon on the image
            if distance < 10 and size_poly > 1:
                polygon = PolyAnnotation(
                    fill_color="blue",
                    fill_alpha=0.2,
                    xs=self.poly_annotation_points_x,
                    ys=self.poly_annotation_points_y,
                )

                self.frame_pane.add_layout(polygon)

                # send the points and reset poly_annotations
                self.rois.append(polygon)
        
                self.poly_annotation_points_x, self.poly_annotation_points_y = [], []
                self.button_save_roi_json.disabled = False
                self._rois_to_json()
                
            else:
                dot = self.frame_pane.scatter(
                    x, y, size=10, color="blue", marker="circle_dot", alpha=0.8
                )
                self.poly_annotation_points_draw.append(dot)

                # Draw line to connect points if we have at least 2 points
                if size_poly > 1:
                    prev_x = self.poly_annotation_points_x[size_poly - 2]
                    prev_y = self.poly_annotation_points_y[size_poly - 2]

                    # Create line between previous and current point
                    line = self.frame_pane.line(
                        [prev_x, x],
                        [prev_y, y],
                        line_color="blue",
                        line_width=2,
                        line_alpha=0.7,
                        line_dash="dashed",
                    )
                    self.poly_lines.append(line)

    def _circle_annotation_old(self, event) -> None:  # Deprecated - now using drag
        if self.select_roi.value == "Circle":  # self.video_loaded and
            self.button_start_tracking.disabled = False
            self.button_clear_roi.disabled = False
            self.button_save_roi_json.disabled = False

            # x and y coordinates
            x = event.x
            y = event.y

            dots_number = len(self.circle_annotation_points)

            if dots_number < 2:
                dot = self.frame_pane.scatter(
                    x, y, size=10, color="green", marker="circle_dot", alpha=0.8
                )
                self.circle_annotation_points.append(dot)
                self.circle_annotation_points_draw.append(dot)
                self.circle_x_y_points.append((x, y))

                dots_number = len(self.circle_annotation_points)

                if dots_number == 2:
                    x0, y0 = self.circle_x_y_points[0]
                    x1, y1 = self.circle_x_y_points[1]
                    radius = ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** (1 / 2)
                    size_value = radius * 2  # Bokeh scatter size is diameter

                    print(
                        f"🔴 CREATING Circle: original_radius={radius}, size_value={size_value}"
                    )
                    circle_draw = self.frame_pane.scatter(
                        [x0],
                        [y0],
                        size=size_value,
                        line_color="green",
                        fill_color="green",
                        fill_alpha=0.3,
                        marker="circle",
                    )
                    self.rois.append(circle_draw)
                
                    # clear dots storage
                    self.circle_annotation_points = []
                    self.circle_x_y_points = []

    def _clear_roi(self, event) -> None:
        try:
            # Method 1: Remove each ROI using the correct Bokeh API
            for roi in self.rois[:]:
                try:
                    # The key insight: ROIs added with add_layout are in self.frame_pane.center
                    if (
                        hasattr(self.frame_pane, "center")
                        and roi in self.frame_pane.center
                    ):
                        self.frame_pane.center.remove(roi)
                        self._add_log_message(f"Removed ROI from center layout", "info")

                    # Also check renderers (for dots/markers)
                    if roi in self.frame_pane.renderers:
                        self.frame_pane.renderers.remove(roi)
                        self._add_log_message(f"Removed ROI from renderers", "info")

                except Exception as e:
                    print(f"Error removing ROI: {e}")

            # Method 2: Clear all layout annotations (brute force)
            if hasattr(self.frame_pane, "center"):
                # Keep only non-ROI elements
                annotations_to_keep = []
                for annotation in self.frame_pane.center[:]:
                    # Keep image and other non-ROI elements
                    annotation_type = str(type(annotation))
                    if (
                        "BoxAnnotation" not in annotation_type
                        and "PolyAnnotation" not in annotation_type
                    ):
                        annotations_to_keep.append(annotation)
                    else:
                        self._add_log_message(f"Removing {annotation_type}", "info")

                # Replace center with only kept annotations
                self.frame_pane.center = annotations_to_keep

            # Method 3: Clear all renderers that might be ROI-related (dots, etc.)
            renderers_to_keep = []
            for renderer in self.frame_pane.renderers[:]:
                renderer_type = str(type(renderer))
                if "image" in renderer_type.lower() or "ImageRGBA" in renderer_type:
                    renderers_to_keep.append(renderer)
                else:
                    self._add_log_message(f"Removing renderer {renderer_type}", "info")

            self.frame_pane.renderers = renderers_to_keep

            # Method 4: Clear dots specifically
            for dot in self.poly_annotation_points_draw[:]:
                if dot in self.frame_pane.renderers:
                    self.frame_pane.renderers.remove(dot)

            for dot in self.circle_annotation_points_draw[:]:
                if dot in self.frame_pane.renderers:
                    self.frame_pane.renderers.remove(dot)

            # Reset all ROI-related data structures
            self.rois = []
        
            # Clear polygon points and connecting lines
            self.poly_annotation_points_draw = []
            self.poly_annotation_points_x = []
            self.poly_annotation_points_y = []

            # Clear polygon connecting lines
            for line in self.poly_lines:
                if line in self.frame_pane.renderers:
                    self.frame_pane.renderers.remove(line)
            self.poly_lines = []

            # Clear circle points
            self.circle_annotation_points = []
            self.circle_annotation_points_draw = []
            self.circle_x_y_points = []

            # Restore background image after clearing
            if hasattr(self, "background") and self.background is not None:
                # Reformat and plot the background
                self.frame_view = self._bokeh_format(self.background)
                width, height = self.background.shape[1], self.background.shape[0]
                self.current_frame = self.frame_pane.image_rgba(
                    image=[self.frame_view], x=0, y=0, dw=width, dh=height
                )
                self._add_log_message(
                    "Background image restored after ROI clearing", "info"
                )
            elif hasattr(self, "current_frame") and self.current_frame is not None:
                # Fallback: use current frame
                self.frame_view = self._bokeh_format(self.current_frame)
                self.current_frame = self.frame_pane.image_rgba(
                    image=[self.frame_view], x=0, y=0, dw=640, dh=640
                )
                self._add_log_message(
                    "Current frame restored after ROI clearing", "info"
                )

            # Update button states
            self.button_clear_roi.disabled = True
            self.button_start_tracking.disabled = True
            self.button_save_roi_json.disabled = True

            # Add log message
            if hasattr(self, "_add_log_message"):
                self._add_log_message("All ROIs cleared - Background restored", "info")

        except Exception as e:
            print(f"Error clearing ROIs: {e}")
            if hasattr(self, "_add_log_message"):
                self._add_log_message(f"Error clearing ROIs: {e}", "error")

    # YOLO Models
    def _update_models_list(self) -> None:
        """Update the list of available YOLO models from the models directory"""
        try:
            if os.path.exists(MODELS_DIR):
                files = os.listdir(MODELS_DIR)
                self.models_name = [file for file in files if file.endswith(".pt")]

                if not self.models_name:
                    self.models_name = [
                        "No models found - Place .pt files in tracking_tab/models/"
                    ]
            else:
                self.models_name = ["Models directory not found"]

        except Exception as e:
            self.models_name = ["Error loading models"]
            print(f"Error loading models: {e}")

    def _update_select_models(self) -> None:
        """Refresh the models dropdown with current available models"""
        self._update_models_list()
        if hasattr(self, "select_model_name"):
            self.select_model_name.options = self.models_name

    def _load_model(self) -> None:
        try:
            model_path = os.path.join(MODELS_DIR, self.select_model_name.value)

            # Check if the selected model is a valid file
            if not self.select_model_name.value.endswith(".pt"):
                error_msg = "Please select a valid .pt model file"
                print(error_msg)
                self._add_log_message(error_msg, "error")
                return

            if not os.path.exists(model_path):
                error_msg = f"Model file not found: {model_path}"
                print(error_msg)
                self._add_log_message(error_msg, "error")
                return

            self._add_log_message(
                f"Loading model: {self.select_model_name.value}", "model"
            )

            # Try to load model with GPU first, fallback to CPU
            try:
                self.yolo_model = YOLO(model_path)
                if self.device == "cuda":
                    self.yolo_model.to("cuda")
                    cuda_info = f"CUDA available - GPU Memory: {cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB"
                    self._add_log_message(cuda_info, "gpu")
                elif self.device == "mps":
                    self.yolo_model.to("mps")
                    self._add_log_message("MPS (Apple Silicon GPU) enabled", "gpu")

                success_msg = f"Model loaded successfully on {self.device.upper()}: {self.select_model_name.value}"
                print(f"🎯 {success_msg}")
                self._add_log_message(success_msg, "model")

            except Exception as gpu_error:
                warning_msg = f"GPU loading failed, trying CPU: {gpu_error}"
                print(f"⚠️  {warning_msg}")
                self._add_log_message(warning_msg, "error")

                self.device = "cpu"
                self.yolo_model = YOLO(model_path)
                success_msg = f"Model loaded on CPU: {self.select_model_name.value}"
                print(f"✅ {success_msg}")
                self._add_log_message(success_msg, "model")

        except Exception as e:
            error_msg = f"Model loading error: {e}"
            print(f"❌ {error_msg}")
            self._add_log_message(error_msg, "error")

    # Video Functions
    def _bokeh_format(self, img: np.ndarray) -> np.ndarray:
        img = Image.fromarray(img)
        img_array = np.array(img.transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA"))
        imview = img_array.view(np.uint32).reshape(img_array.shape[:2])

        return imview

    def _load_video(self, event) -> None:
        self.video_loaded = False

        mime_to_ext = {"video/mp4": ".mp4", "video/avi": ".avi"}

        if self.file_input.value is not None:
            video_format = self.file_input.mime_type

            # tmp file to store video
            self.tmp_file = os.path.join(
                TEMP_DIR, "tmp_file" + mime_to_ext[video_format]
            )

            try:
                with open(self.tmp_file, "wb") as tmp:
                    tmp.write(event)
                print("Temporary file created successfully")
                self.video_loaded = True
            except Exception as e:
                print(f"Error {e}")
                return

            # only happens if the temp_file is created successfully
            if self.video_loaded:
                self._calculate_background()

    def _calculate_background(self) -> None:
        try:
            cap = cv.VideoCapture(self.tmp_file)
            total_frames = int(cap.get(cv.CAP_PROP_FRAME_COUNT))
            self.total_frames = total_frames  # Store for progress tracking

            if not cap.isOpened():
                self.warning.object = "## Alert\n Video couldn't be loaded!"
                self.warning.visible = True
                self._thread_hide_warning()
                return

            sample_ret, sample_frame = cap.read()

            if not sample_ret:
                self.warning.object = "## Alert\n Couldn't grab video info!"
                self.warning.visible = True
                self._thread_hide_warning()
                return

            # display progress bar
            self.progress_bar.visible = True
            self.progress_bar.value = 0

            # Reset video position
            cap.set(cv.CAP_PROP_POS_FRAMES, 0)

            # Initialize frame accumulator
            # sample_frame = cv.resize(sample_frame, YOLO_RESOLUTION)
            frame_count = 0
            median_accumulator = np.zeros_like(sample_frame, dtype=np.float32)

            # Sample frames to calculate background (not processing every frame for efficiency)
            # Use frame sampling to process approximately 200 frames
            total_samples = min(200, total_frames)
            frame_step = max(1, total_frames // total_samples)

            height, width, _ = sample_frame.shape

            # redefine figure axis
            self.frame_pane.width = width
            self.frame_pane.height = height
            self.frame_pane.x_range = Range1d(0, width)
            self.frame_pane.y_range = Range1d(0, height)

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

                # guarantee that warning is not visible when the progress bar is plotted
                self.warning.visible = False

                # update progress bar value
                self.progress_bar.name = "Loading video background..."
                self.progress_bar.value = int(current_frame / total_frames * 100)

                # Move to next frame to sample
                current_frame += frame_step

            self.progress_bar.visible = False
            cap.release()

            if frame_count == 0:
                self.warning.object = "No frames were processed"
                self.warning.visible = True
                self._thread_hide_warning()
                return

            # Calculate the average (approximating median for efficiency)
            self.background = (median_accumulator / frame_count).astype(np.uint8)

            # Save the background image in models folder
            background_path = os.path.join(MODELS_DIR, "background.png")
            cv.imwrite(background_path, self.background)

            # Create grayscale version for template matching
            self.background_frame = cv.cvtColor(self.background, cv.COLOR_RGB2GRAY)

            # Convert to bokeh format
            # frame_pil = Image.fromarray(background)
            # frame_array = np.array(frame_pil.transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA"))
            # self.frame_view = frame_array.view(np.uint32).reshape(frame_array.shape[:2])

            self.frame_view = self._bokeh_format(self.background)
            self.current_frame = self.frame_pane.image_rgba(
                image=[self.frame_view], x=0, y=0, dw=width, dh=height
            )
            # self.current_frame.data_source.data["image"] = [self.frame_view]

        except Exception as e:
            print(f"Background calculation error: {e}")

    # Tracking
    def _start_tracking(self, event) -> None:
        print("=" * 50)
        print("🚀 START TRACKING FUNCTION CALLED!")
        print(
            f"Start tracking clicked. ROIs: {len(self.rois)}, video_loaded: {self.video_loaded}"
        )
        print("=" * 50)

        if self.yolo_model is None:
            self.progress_bar.name = "Loading YOLO model..."
            self.progress_bar.visible = True
            self.progress_bar.value = -1
            self._load_model()

            shape = (self.frame_pane.height, self.frame_pane.width)

            self.mask = create_roi_mask(rois=self.rois, frame_shape=shape)

        if self.yolo_model is not None:
            # Configure progress bar for tracking
            self.progress_bar.name = (
                f"Tracking Progress (0 / {self.total_frames} frames)"
            )
            self.progress_bar.visible = True
            self.progress_bar.value = 0
            self.progress_bar.max = self.total_frames
            self.button_pause_tracking.disabled = False
            self.button_stop_tracking.disabled = False
            self.button_start_tracking.disabled = True

            # Always update roi_in_track to current ROIs for new tracking session
            if len(self.rois) > 0:
                self.roi_in_track = (
                    self.rois.copy()
                )  # Make a copy to avoid reference issues
            else:
                return  # Don't start tracking without ROIs

            self._clear_roi(event)
            self.tracking_log.visible = True
            self.tracking_paused = False

            self._add_log_message(
                f"Starting tracking with {len(self.roi_in_track) if self.roi_in_track else 0} ROIs",
                "info",
            )
            self._add_log_message(
                f"Frame processing rate: ~30 FPS (33ms interval)", "info"
            )

            self.callback_tracking = pn.state.add_periodic_callback(
                lambda: self._capture_tracking_frame(self.roi_in_track), 33
            )

    def _pause_tracking(self, event) -> None:
        """Pause/Resume tracking - keeps all data and settings"""
        if self.tracking_paused:
            # Resume tracking
            self.tracking_paused = False
            self.button_pause_tracking.name = "⏸ Pause"
            self.button_pause_tracking.button_type = "warning"
            self._add_log_message(
                "▶ Tracking resumed - continuing from where it stopped", "info"
            )
        else:
            # Pause tracking
            self.tracking_paused = True
            self.button_pause_tracking.name = "▶ Resume"
            self.button_pause_tracking.button_type = "success"
            self._add_log_message("⏸ Tracking paused - data preserved", "info")

        self._update_tracking_log()

    def _stop_tracking(self, event) -> None:
        """Stop tracking and clean up"""
        if hasattr(self, "callback_tracking") and self.callback_tracking:
            self.callback_tracking.stop()

        # Hide progress bar when stopping
        self.progress_bar.visible = False
        self._add_log_message(
            "🛑 Tracking stopped - Cleaning up current experiment", "info"
        )
        self._cleanup_experiment()
        if self.video_loaded:
            self._add_log_message(
                "🔄 Ready for new experiment with same video", "success"
            )
        else:
            self._add_log_message(
                "📁 Ready for new experiment - please load a video", "info"
            )

    def _cleanup_experiment(self) -> None:
        """Clean up experiment and reset interface"""
        # Reset button states (with safety checks)
        if hasattr(self.button_start_tracking, "disabled"):
            self.button_start_tracking.disabled = True
        if hasattr(self.button_pause_tracking, "disabled"):
            self.button_pause_tracking.disabled = True
        if hasattr(self.button_stop_tracking, "disabled"):
            self.button_stop_tracking.disabled = True
        if hasattr(self.button_save_roi_json, "disabled"):
            self.button_save_roi_json.disabled = True
        if hasattr(self.button_download_json, "disabled"):
            self.button_download_json.disabled = True

        # Reset tracking state
        self.tracking_paused = False
        self.button_pause_tracking.name = "⏸ Pause"
        self.button_pause_tracking.button_type = "warning"

        # Clear tracking data but keep ROI reference for new experiment
        self.tracking_data = []
        self.frame_count = 0
        self.no_detection_count = 0
        self.yolo_detections = 0
        self.template_detections = 0
        # Don't clear roi_in_track - will be updated on next start

        # Reset progress bar
        self.progress_bar.visible = False
        self.progress_bar.value = 0
        self.progress_bar.name = "Progress"

        # Clear ROIs first
        self._clear_roi(None)

        # Clear all ROI data
        self.rois = []
        self.roi_dots = []
        self.roi_lines = []
        self.circle_roi_data = {}  # Clear circle data storage

        # Reset frame display to show clean background for new experiment
        if (
            hasattr(self, "background")
            and self.background is not None
            and self.video_loaded
        ):
            # Show the clean background image ready for new ROI drawing
            self.current_frame = self.background.copy()
            width, height = self.background.shape[1], self.background.shape[0]
            self.frame_view = self._bokeh_format(self.current_frame)

            # Clear frame pane and show background
            self.frame_pane.renderers = []
            self.current_frame = self.frame_pane.image_rgba(
                image=[self.frame_view], x=0, y=0, dw=width, dh=height
            )

            # Update frame pane dimensions to match video
            self.frame_pane.width = width
            self.frame_pane.height = height
            self.frame_pane.x_range = Range1d(0, width)
            self.frame_pane.y_range = Range1d(0, height)
        else:
            # Fallback to gray background if no video loaded
            self.current_frame = np.ones(YOLO_RESOLUTION, dtype=np.uint8) * 240
            self.frame_view = self._bokeh_format(self.current_frame)

            # Clear frame pane and show default dimensions
            self.frame_pane.renderers = []
            self.frame_pane.image_rgba(
                image=[self.frame_view], x=0, y=0, dw=640, dh=640
            )

            # Reset to default dimensions
            self.frame_pane.width = 640
            self.frame_pane.height = 640
            self.frame_pane.x_range = Range1d(0, 640)
            self.frame_pane.y_range = Range1d(0, 640)

        # Hide tracking log
        self.tracking_log.visible = False
        self.log_messages = []

        # Keep video loaded and background for new experiment
        # Don't reset: self.video_loaded, self.background, self.background_frame
        # Don't clear: file_input (keep the video file loaded)

        # Don't remove temp files - keep video available for new experiments
        # self._cleanup_temp_files()  # Only remove when completely done with video

    def _capture_tracking_frame(self, rois: list) -> None:
        try:
            # Skip processing if paused
            if self.tracking_paused:
                return

            cap = cv.VideoCapture(self.tmp_file)

            for _ in range(self.frame_count - 1):
                cap.grab()

            ret, frame = cap.read()

            if not ret or self.frame_count >= self.total_frames:
                # Configure download when tracking completes
                self._configure_download()
                self.button_download_json.disabled = False
                self.callback_tracking.stop()
                # Hide progress bar when tracking completes
                self.progress_bar.visible = False
                if not ret:
                    self._add_log_message(
                        "✅ Tracking completed successfully!", "success"
                    )
                else:
                    self._add_log_message(
                        "✅ Tracking completed - reached end of video!", "success"
                    )
                return

            # process frames and update log params
            frame = process_frame(frame, self.yolo_model, self.frame_count, self)

            # draw rois in image
            frame = draw_rois(image=frame, rois=rois, circle_data=self.circle_roi_data)

            # Update progress bar
            if self.total_frames > 0:
                # Ensure frame_count doesn't exceed total_frames to avoid progress bar error
                current_frame = min(self.frame_count, self.total_frames)
                progress_percent = (current_frame / self.total_frames) * 100
                self.progress_bar.value = current_frame
                self.progress_bar.name = f"Tracking Progress ({current_frame} / {self.total_frames} frames) - {progress_percent:.1f}%"

            # update tracking log
            self._update_tracking_log()

            self.frame_view = self._bokeh_format(frame)
            self.current_frame.data_source.data["image"] = [self.frame_view]

        except Exception as e:
            error_msg = f"Error in capturing frame: {e}"
            print(error_msg)
            self._add_log_message(error_msg, "error")
            self._update_tracking_log()
            self.callback_tracking.stop()

    def _add_log_message(self, message: str, msg_type: str = "info") -> None:
        """Add a log message with timestamp and type"""
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        if msg_type == "error":
            formatted_msg = f"🔴 [{timestamp}] ERROR: {message}"
        elif msg_type == "gpu":
            formatted_msg = f"🟢 [{timestamp}] GPU: {message}"
        elif msg_type == "model":
            formatted_msg = f"🔵 [{timestamp}] MODEL: {message}"
        else:
            formatted_msg = f"⚪ [{timestamp}] INFO: {message}"

        self.log_messages.append(formatted_msg)
        # Keep only last 20 messages to avoid memory issues
        if len(self.log_messages) > 20:
            self.log_messages.pop(0)

    def _update_tracking_log(self) -> None:
        # Main tracking stats
        log_text = (
            f"### 📊 Tracking Status\n\n"
            f"**Device:** {self.device}\n\n"
            f"**Total Frames:** {self.frame_count}\n\n"
            f"**Frames without detection:** {self.no_detection_count}\n\n"
            f"**YOLO detections:** {self.yolo_detections}\n\n"
            f"**Template detections:** {self.template_detections}\n\n"
        )


        if self.tracking_data and len(self.tracking_data) > 0:
            last_frame = self.tracking_data[-1]
            log_text += (
                f"**Last Centroid X:** {last_frame.get('centroid_x', 'N/A')}\n\n"
            )
            log_text += (
                f"**Last Centroid Y:** {last_frame.get('centroid_y', 'N/A')}\n\n"
            )

        # Add recent log messages
        if self.log_messages:
            log_text += "---\n\n### 📝 Recent Logs\n\n"
            for msg in self.log_messages[-10:]:  # Show last 10 messages
                log_text += f"{msg}\n\n"

        self.tracking_log.object = log_text

    def _hide_warning(self) -> None:
        self.warning.visible = False

    def _rois_to_json(self) -> None:
        # ROI export functionality removed - ROIs are now included in the main tracking data export
        import json
        from datetime import datetime

        try:
            # Validate required data
            if not len(self.rois):
                self._add_log_message("❌ No ROI loaded for download", "error")
                return

            json_string = json.dumps(convert_rois_to_dict(self.rois), indent=2)

            timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")

            filename = f"rois_data_{timestamp}.json"
            data_bytes = json_string.encode("utf-8")

            # Create BytesIO object from the data
            file_obj = BytesIO(data_bytes)
            file_obj.seek(0)  # Ensure we're at the start of the data
            
            # Configure FileDownload widget
            self.button_save_roi_json.file = file_obj
            self.button_save_roi_json.filename = filename
            self.button_save_roi_json.mime_type = "application/json"
            
        except Exception as e:
            self._add_log_message(f"❌ Error preparing download: {str(e)}", "error")
            print(f"Error configuring download: {e}")
            import traceback

            traceback.print_exc()    
        
    def _configure_download(self) -> None:
        """Configure the download button with tracking data"""
        try:
            # Validate required data
            if not hasattr(self.file_input, "filename") or not self.file_input.filename:
                self._add_log_message("❌ No video file loaded for download", "error")
                return

            if not self.tracking_data:
                self._add_log_message(
                    "❌ No tracking data available for download", "error"
                )
                return

            filename = create_download_filename(self.file_input.filename)
            
            data_bytes = export_tracking_data(
                filename,
                self.select_experiment_type.value,
                self.frame_count,
                self.no_detection_count,
                self.yolo_detections,
                self.template_detections,
                self.roi_in_track if self.roi_in_track else [],  # Use roi_in_track instead of self.rois
                self.tracking_data,
                self.circle_roi_data,  # Pass circle ROI data
                self.frame_pane.height,  # Pass frame height for coordinate conversion
            )

            # Create BytesIO object from the data
            file_obj = BytesIO(data_bytes)
            file_obj.seek(0)  # Ensure we're at the start of the data

            # Configure FileDownload widget
            self.button_download_json.file = file_obj
            self.button_download_json.filename = filename
            self.button_download_json.mime_type = "application/json"

            self._add_log_message(f"✅ Download ready: {filename}", "success")
            print(f"Download configured successfully: {filename}")

        except Exception as e:
            self._add_log_message(f"❌ Error preparing download: {str(e)}", "error")
            print(f"Error configuring download: {e}")
            import traceback

            traceback.print_exc()

    def get_panel(self) -> pn.Column:
        # Create info accordion
        info_accordion = pn.Accordion(
            ("ℹ️ About Tracking", pn.pane.Markdown(
                "Track animals using YOLOv11 segmentation masks and save tracking data to .json format.\n\n"
                "**Recorded data:**\n"
                "- X,Y coordinates of animal's center of mass (calculated from segmentation mask)\n"
                "- ROI positioning information (which ROI the animal is in)\n"
                "- Frame-by-frame tracking metadata\n\n"
                "All data is stored in JSON format for future analysis and visualization."
            )),
            active=[],  # Collapsed by default
            width=900,
        )

        # YOLO Settings Accordion
        yolo_settings_accordion = pn.Accordion(
            ("⚙️ YOLO Settings - Configure YOLO model and detection parameters",
             pn.Column(
                self.select_model_name,
                pn.Row(self.slider_confidence, self.slider_iou),
                self.file_input,
                pn.Spacer(height=15),
             )),
            active=[],  # Collapsed by default
            width=900,
        )

        # Experiment Settings Accordion
        experiment_settings_accordion = pn.Accordion(
            ("🐁 Experiment Settings - Define experiment type, ROIs and tracking controls",
             pn.Column(
                pn.Row(self.select_experiment_type, self.select_roi),
                pn.Spacer(height=15),
                pn.Row(
                    pn.Column(
                        pn.pane.Markdown("**🎮 Tracking Controls**"),
                        pn.Row(
                            self.button_start_tracking,
                            pn.Spacer(width=8),
                            self.button_pause_tracking,
                            pn.Spacer(width=8),
                            self.button_stop_tracking,
                        ),
                        width=320,
                    ),
                    pn.Spacer(width=20),
                    pn.Column(
                        pn.pane.Markdown("**🎯 ROI Tools**"),
                        pn.Row(
                            self.button_clear_roi,
                            pn.Spacer(width=15),
                            self.button_save_roi_json,
                        ),
                        width=200,
                    ),
                ),
                pn.Spacer(height=15),
             )),
            active=[],  # Collapsed by default
            width=900,
        )

        return pn.Column(
            pn.pane.Markdown("## Tracking"),
            info_accordion,
            pn.Spacer(height=10),
            yolo_settings_accordion,
            pn.Spacer(height=10),
            experiment_settings_accordion,
            pn.Spacer(height=15),
            self.warning,
            self.progress_bar,
            self.frame_pane,
            pn.Spacer(height=10),
            pn.Row(
                pn.pane.Markdown("**📊 Results**"),
                pn.Spacer(width=20),
                self.button_download_json,
            ),
            self.tracking_log,
            margin=(10, 0),
        )


def get_tab() -> pn.Column:
    track = TrackingTab()
    return track.get_panel()
