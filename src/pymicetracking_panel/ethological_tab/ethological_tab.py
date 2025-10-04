from pathlib import Path

import panel as pn

from .file_handler import FileHandler
from .heatmap_analysis import HeatmapAnalysis
from .open_field import OpenFieldTab
from .video_analysis import VideoAnalysis


class EthologicalTab:
    def __init__(self) -> None:
        # Get paths
        self.project_root = Path(__file__).parent.parent
        self.experiments_dir = self.project_root / "experiments"
        self.temp_dir = Path(__file__).parent / "temp"

        # Clean and create temp directory
        self._cleanup_temp_files()
        self.temp_dir.mkdir(exist_ok=True)

        # Initialize handlers
        self.file_handler = FileHandler(self.project_root)
        self.video_analysis = VideoAnalysis(self.temp_dir, self.project_root)
        self.heatmap_analysis = HeatmapAnalysis(self.temp_dir)
        self.open_field_tab = OpenFieldTab(self.project_root, self.temp_dir)

        # Video Analysis components
        self.video_input = pn.widgets.FileInput(
            accept=".mp4,.avi,.mov,.mkv",
            name="📹 Select Video File:",
            width=400,
            multiple=False,
        )

        self.json_input = pn.widgets.FileInput(
            accept=".json", name="📄 Select JSON File:", width=400, multiple=False
        )

        self.show_info_panel = pn.widgets.Checkbox(
            name="Show Info Panel on Video", value=False, width=200
        )

        self.show_heatmap = pn.widgets.Checkbox(
            name="Show Heatmap on Video", value=False, width=200
        )

        self.start_analysis_button = pn.widgets.Button(
            name="🚀 Start Analysis",
            button_type="success",
            width=150,
            height=40,
            disabled=True,
        )

        self.abort_button = pn.widgets.Button(
            name="❌ Abort Analysis",
            button_type="danger",
            width=150,
            height=40,
            disabled=True,
            visible=False,
        )

        # Progress and results
        self.analysis_progress = pn.indicators.Progress(
            name="Analysis Progress", value=0, max=100, width=400, visible=False
        )

        # Unified status panel
        self.unified_status = pn.pane.Markdown(
            "**Status:** Ready\n\nSelect video and JSON files to start analysis.",
            styles={"background": "#f8f9fa", "padding": "15px", "border-radius": "5px"},
            width=550,
            min_height=250,
        )

        # Download button component
        self.download_button = pn.widgets.FileDownload(
            label="📥 Download Result",
            button_type="success",
            width=150,
            height=40,
            disabled=True,
            visible=False,
            auto=False,
        )

        # Movement Heatmap Analysis components
        self.heatmap_json_input = pn.widgets.FileInput(
            accept=".json", name="📊 Select Tracking JSON:", width=400, multiple=False
        )

        self.export_format = pn.widgets.RadioBoxGroup(
            name="Export Format:",
            value="png",
            options=["png", "eps"],
            inline=True,
            width=200,
        )

        # Heatmap configuration
        self.heatmap_bins = pn.widgets.IntSlider(
            name="Heatmap Resolution (bins):",
            start=20,
            end=100,
            step=10,
            value=50,
            width=300,
        )

        self.heatmap_colormap = pn.widgets.Select(
            name="Heatmap Colormap:",
            value="hot",
            options=["hot", "viridis", "plasma", "jet", "rainbow", "coolwarm"],
            width=200,
        )

        self.heatmap_alpha = pn.widgets.FloatSlider(
            name="Heatmap Transparency:",
            start=0.5,
            end=1.0,
            step=0.1,
            value=0.8,
            width=200,
        )

        # Movement analysis configuration
        self.movement_threshold_percentile = pn.widgets.IntSlider(
            name="Movement Threshold (percentile):",
            start=50,
            end=95,
            step=5,
            value=75,
            width=300,
        )

        self.velocity_bins = pn.widgets.IntSlider(
            name="Velocity Histogram Bins:",
            start=15,
            end=50,
            step=5,
            value=30,
            width=300,
        )

        # Analysis type selection
        self.analysis_type = pn.widgets.Select(
            name="Analysis Type:",
            value="complete",
            options={
                "Complete Panel": "complete",
                "Individual Plots": "individual",
            },
            width=200,
        )

        self.generate_analysis_button = pn.widgets.Button(
            name="📊 Generate Analysis (JSON required)",
            button_type="primary",
            width=250,
            height=40,
            disabled=True,
        )

        # Download button for generated image
        self.download_heatmap_button = pn.widgets.Button(
            name="💾 Download Image",
            button_type="success",
            width=150,
            height=40,
            disabled=True,
            visible=False,
        )

        self.heatmap_status = pn.pane.Markdown(
            "**Status:** Ready\n\nSelect a tracking JSON file to start analysis.",
            styles={"background": "#f8f9fa", "padding": "15px", "border-radius": "5px"},
            width=550,
            min_height=250,
        )

        # Connect events
        self.video_input.param.watch(self._on_file_selected, "value")
        self.video_input.param.watch(self._on_file_selected, "filename")
        self.json_input.param.watch(self._on_file_selected, "value")
        self.json_input.param.watch(self._on_file_selected, "filename")
        self.heatmap_json_input.param.watch(self._on_heatmap_json_selected, "value")
        self.heatmap_json_input.param.watch(self._on_heatmap_json_selected, "filename")
        self.start_analysis_button.on_click(self._start_analysis)
        self.abort_button.on_click(self._abort_analysis)
        # FileDownload widget doesn't need on_click - it handles download automatically
        self.generate_analysis_button.on_click(self._generate_complete_analysis)
        self.download_heatmap_button.on_click(self._download_analysis_image)

    def _cleanup_temp_files(self) -> None:
        """Clean up temporary files from previous sessions"""
        temp_dir = Path(__file__).parent / "temp"
        if temp_dir.exists():
            import shutil

            try:
                shutil.rmtree(temp_dir)
                print(f"[CLEANUP] Removed temporary files from: {temp_dir}")
            except Exception as e:
                print(f"[CLEANUP] Warning: Could not clean temp directory: {e}")

    def _on_file_selected(self, event) -> None:
        """Handle file selection for both video and JSON"""
        self._update_files_status()

    def _update_files_status(self) -> None:
        """Update status based on selected files"""
        has_video = self.video_input.value and len(self.video_input.value) > 0
        has_json = self.json_input.value and len(self.json_input.value) > 0

        if not has_video and not has_json:
            self._update_unified_status(
                "**Status:** Ready\n\nSelect video and JSON files to start analysis.",
                "#f8f9fa",
            )
            self.start_analysis_button.disabled = True
            return

        if not has_video:
            self._update_unified_status(
                "**Status:** ❌ Video file required\n\nPlease select a video file to continue.",
                "#f8d7da",
            )
            self.start_analysis_button.disabled = True
            return

        if not has_json:
            self._update_unified_status(
                "**Status:** ❌ JSON file required\n\nPlease select a JSON tracking file to continue.",
                "#f8d7da",
            )
            self.start_analysis_button.disabled = True
            return

        # Both files selected - validate JSON
        try:
            # Create temporary JSON file to validate
            temp_json_path = self.project_root / "temp_json_for_validation.json"

            if self.file_handler.validate_uploaded_json(
                self.json_input.value, temp_json_path
            ):
                video_filename = getattr(self.video_input, "filename", "video_file.mp4")
                json_filename = getattr(self.json_input, "filename", "data.json")

                video_size_mb = len(self.video_input.value) / 1024 / 1024
                status_msg = (
                    f"**Status:** ✅ Ready to analyze\n\n"
                    f"**Video:** {video_filename} ({video_size_mb:.1f} MB)\n"
                    f"**JSON:** {json_filename}\n\n"
                    f"Click 'Start Analysis' to begin processing."
                )
                self._update_unified_status(status_msg, "#d1ecf1")

                self.start_analysis_button.disabled = False
            else:
                self._update_unified_status(
                    "**Status:** ❌ Invalid JSON format\n\n"
                    "The JSON file doesn't contain valid tracking data. "
                    "Please select a proper tracking JSON file.",
                    "#f8d7da",
                )
                self.start_analysis_button.disabled = True

        except Exception as e:
            self._update_unified_status(
                f"**Status:** ❌ Error validating JSON\n\n"
                f"{str(e)}\n\n"
                f"Please check your JSON file format.",
                "#f8d7da",
            )
            self.start_analysis_button.disabled = True

    def _update_unified_status(self, message: str, background_color: str) -> None:
        """Update unified status panel"""
        self.unified_status.object = message
        self.unified_status.styles = {
            "background": background_color,
            "padding": "15px",
            "border-radius": "5px",
        }

    def _on_heatmap_json_selected(self, event) -> None:
        """Handle heatmap JSON file selection"""
        self._update_heatmap_status()

    def _update_heatmap_status(self) -> None:
        """Update heatmap analysis status based on selected JSON"""
        has_json = (
            self.heatmap_json_input.value and len(self.heatmap_json_input.value) > 0
        )

        if not has_json:
            self._update_heatmap_status_panel(
                "**Status:** Ready\n\n"
                "Select a tracking JSON file to start analysis.",
                "#f8f9fa",
            )
            self.generate_analysis_button.disabled = True
            return

        # Validate JSON file
        try:
            # Create temporary JSON file to validate
            temp_json_path = self.project_root / "temp_heatmap_json_for_validation.json"

            if self.file_handler.validate_uploaded_json(
                self.heatmap_json_input.value, temp_json_path
            ):
                json_filename = getattr(
                    self.heatmap_json_input, "filename", "data.json"
                )
                json_size_kb = len(self.heatmap_json_input.value) / 1024

                status_msg = (
                    f"**Status:** ✅ Ready to analyze\n\n"
                    f"**JSON:** {json_filename} ({json_size_kb:.1f} KB)\n\n"
                    f"Configure parameters and click Generate Complete Analysis."
                )
                self._update_heatmap_status_panel(status_msg, "#d1ecf1")

                self.generate_analysis_button.disabled = False
            else:
                self._update_heatmap_status_panel(
                    "**Status:** ❌ Invalid JSON format\n\n"
                    "The JSON file doesn't contain valid tracking data.",
                    "#f8d7da",
                )
                self.generate_analysis_button.disabled = True

        except Exception as e:
            self._update_heatmap_status_panel(
                f"**Status:** ❌ Error validating JSON\n\n{str(e)}", "#f8d7da"
            )
            self.generate_analysis_button.disabled = True

    def _update_heatmap_status_panel(self, message: str, background_color: str) -> None:
        """Update heatmap status panel"""
        self.heatmap_status.object = message
        self.heatmap_status.styles = {
            "background": background_color,
            "padding": "15px",
            "border-radius": "5px",
        }

    def _start_analysis(self, event) -> None:
        """Start ethological analysis"""
        if not self.video_input.value or not self.json_input.value:
            return

        # Start analysis mode
        self.start_analysis_button.disabled = True
        self.abort_button.visible = True
        self.abort_button.disabled = False
        self.analysis_progress.visible = True
        self.analysis_progress.value = 0
        self.download_button.visible = False

        # Get filenames
        video_filename = getattr(self.video_input, "filename", "video_file.mp4")
        json_filename = getattr(self.json_input, "filename", "data.json")

        self.video_analysis.start_analysis(
            self.video_input.value,
            self.json_input.value,
            video_filename,
            json_filename,
            self.show_info_panel.value,
            self.show_heatmap.value,
            self._update_progress,
            self._update_unified_status,
            self.download_button,  # Pass download button to configure it
        )

    def _update_progress(self, value: int) -> None:
        """Update analysis progress"""
        self.analysis_progress.value = value

        # When analysis is complete, update UI
        if value >= 100:
            self._reset_analysis_ui()

    def _abort_analysis(self, event) -> None:
        """Abort the current analysis"""
        self.video_analysis.abort_analysis()
        self._update_unified_status(
            "**Status:** ❌ **Analysis Aborted by User**\n\nAnalysis process was cancelled.",
            "#f8d7da",
        )
        self._reset_analysis_ui()

    # _download_file method removed - FileDownload widget handles this automatically

    def _generate_complete_analysis(self, event) -> None:
        """Generate complete movement analysis with heatmap and statistics"""
        if not self.heatmap_json_input.value:
            return

        json_filename = getattr(self.heatmap_json_input, "filename", "data.json")

        self.heatmap_analysis.generate_complete_analysis(
            self.heatmap_json_input.value,
            json_filename,
            self.analysis_type.value,
            self.export_format.value,
            self.heatmap_bins.value,
            self.heatmap_colormap.value,
            self.heatmap_alpha.value,
            self.movement_threshold_percentile.value,
            self.velocity_bins.value,
            self._update_heatmap_status_panel,
        )

        # Enable download button if analysis generated successfully
        if self.heatmap_analysis.current_analysis_path:
            self.download_heatmap_button.disabled = False
            self.download_heatmap_button.visible = True

    def _download_analysis_image(self, event) -> None:
        """Handle download button click for analysis images"""
        self.heatmap_analysis.download_analysis_image(self._update_heatmap_status_panel)

    def _reset_analysis_ui(self) -> None:
        """Reset UI to ready state"""
        self.analysis_progress.visible = False
        self.analysis_progress.value = 0

        # Check if we can enable start button
        has_video = self.video_input.value and len(self.video_input.value) > 0
        has_json = self.json_input.value and len(self.json_input.value) > 0
        self.start_analysis_button.disabled = not (has_video and has_json)

        self.abort_button.visible = False
        self.abort_button.disabled = True

        # Keep download button visible if analysis was completed
        if (
            self.video_analysis.current_output_path
            and self.video_analysis.current_output_path.exists()
        ):
            self.download_button.visible = True
            self.download_button.disabled = False
        else:
            self.download_button.visible = False
            self.download_button.disabled = True

    def get_panel(self) -> pn.Column:
        """Return the main panel layout"""
        return pn.Column(
            pn.pane.Markdown("# 🧬 Ethological Analysis", margin=(0, 0, 20, 0)),
            # Video Tracking Analysis
            pn.pane.Markdown("## 📹 Video Tracking Analysis: Generates a video with tracking for visualization only", margin=(0, 0, 10, 0)),
            pn.Row(
                # Left side - File inputs and options
                pn.Column(
                    pn.pane.Markdown("**File Selection:**", margin=(0, 0, 10, 0)),
                    self.video_input,
                    self.json_input,
                    pn.Spacer(height=15),
                    pn.pane.Markdown("**Analysis Options:**", margin=(0, 0, 10, 0)),
                    self.show_info_panel,
                    self.show_heatmap,
                    pn.Spacer(height=15),
                    pn.pane.Markdown("**Analysis Controls:**", margin=(0, 0, 10, 0)),
                    pn.Row(
                        self.start_analysis_button,
                        self.abort_button,
                        self.download_button,
                    ),
                    styles={
                        "background": "#f8f4e6",
                        "padding": "20px",
                        "border-radius": "8px",
                        "margin": "10px"
                    },
                    width=480,
                ),
                pn.Spacer(width=20),
                # Right side - Status only
                pn.Column(self.unified_status, width=570),
            ),
            pn.Spacer(height=15),
            # Progress only
            self.analysis_progress,
            pn.Spacer(height=30),
            pn.pane.Markdown("---"),
            pn.Spacer(height=20),
            # Movement Heatmap Analysis
            pn.pane.Markdown("## 🔥 Movement Analysis: Generates velocity figure and cumulative heatmap, plus a .json file with velocity data", margin=(0, 0, 10, 0)),
            pn.Row(
                # Left side - File inputs and configuration
                pn.Column(
                    self.heatmap_json_input,
                    pn.Spacer(height=15),
                    # Heatmap Parameters
                    pn.pane.Markdown("**📊 Heatmap Parameters:**", margin=(0, 0, 8, 0)),
                    pn.Column(
                        self.heatmap_bins,
                        pn.Row(
                            self.heatmap_colormap,
                            pn.Spacer(width=10),
                            self.heatmap_alpha,
                        ),
                        styles={
                            "background": "#f0f8ff",
                            "padding": "10px",
                            "border-radius": "5px",
                        },
                    ),
                    pn.Spacer(height=12),
                    # Velocity Analysis Parameters
                    pn.pane.Markdown("**📈 Velocity Analysis Parameters:**", margin=(0, 0, 8, 0)),
                    pn.Column(
                        self.movement_threshold_percentile,
                        self.velocity_bins,
                        styles={
                            "background": "#fff8f0",
                            "padding": "10px",
                            "border-radius": "5px",
                        },
                    ),
                    pn.Spacer(height=15),
                    pn.pane.Markdown("**Export & Analysis Options:**", margin=(0, 0, 8, 0)),
                    pn.Row(
                        pn.Column(
                            pn.pane.Markdown("Export Format:", margin=(0, 0, 5, 0)),
                            self.export_format,
                        ),
                        pn.Spacer(width=15),
                        pn.Column(
                            self.analysis_type,
                        ),
                    ),
                    pn.Spacer(height=15),
                    pn.pane.Markdown("**Actions:**", margin=(0, 0, 8, 0)),
                    pn.Row(
                        self.generate_analysis_button,
                        pn.Spacer(width=10),
                        self.download_heatmap_button,
                    ),
                    styles={
                        "background": "#e8f5f0",
                        "padding": "20px",
                        "border-radius": "8px",
                        "margin": "10px"
                    },
                    width=500,
                ),
                pn.Spacer(width=20),
                # Right side - Status
                pn.Column(self.heatmap_status, width=570),
            ),
            pn.Spacer(height=30),
            pn.pane.Markdown("---"),
            pn.Spacer(height=20),
            # Open Field Analysis
            pn.pane.Markdown("## 🔵 Open Field: Circular arena for anxiety behavior analysis", margin=(0, 0, 10, 0)),
            self.open_field_tab.get_panel(),
            pn.Spacer(height=30),
            pn.pane.Markdown("---"),
            pn.Spacer(height=20),
            # Elevated Plus Maze Analysis
            pn.pane.Markdown("## 🟣 Elevated Plus Maze: Specific analysis for Elevated Plus Maze experiments", margin=(0, 0, 10, 0)),
            pn.pane.Markdown("*Coming soon...*", styles={"color": "#888", "font-style": "italic"}),
            margin=(20, 20),
        )


def get_tab() -> pn.Column:
    """Create and return the Ethological Analysis tab"""
    ethological = EthologicalTab()
    return ethological.get_panel()
