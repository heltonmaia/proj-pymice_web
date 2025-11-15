import base64
import json
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np
import panel as pn
import scipy.ndimage as ndimage


class HeatmapAnalysis:
    """Handles movement heatmap analysis for ethological data"""

    def __init__(self, temp_dir: Path) -> None:
        self.temp_dir = temp_dir
        self.current_analysis_path = None

    def generate_complete_analysis(
        self,
        json_value: bytes,
        json_filename: str,
        analysis_type: str,
        export_format: str,
        heatmap_bins: int,
        heatmap_colormap: str,
        heatmap_alpha: float,
        movement_threshold_percentile: int,
        velocity_bins: int,
        status_callback: Callable[[str, str], None],
    ) -> None:
        """Generate complete movement analysis with heatmap and statistics"""
        if not json_value:
            return

        try:
            if analysis_type == "complete":
                status_callback(
                    (
                        "**Status:** 🔄 Generating complete analysis panel...\n\n"
                        "Processing tracking data..."
                    ),
                    "#fff3cd",
                )
            else:
                status_callback(
                    (
                        "**Status:** 🔄 Generating individual plots...\n\n"
                        "Processing tracking data..."
                    ),
                    "#fff3cd",
                )

            # Load tracking data
            temp_json_path = self.temp_dir / "temp_complete_analysis.json"
            with open(temp_json_path, "wb") as f:
                f.write(json_value)

            with open(temp_json_path, "r") as f:
                data = json.load(f)

            tracking_data = data.get("tracking_data", [])
            if not tracking_data:
                status_callback("**Status:** ❌ No tracking data found", "#f8d7da")
                return

            # Extract positions and frame numbers
            frames = []
            x_positions = []
            y_positions = []
            total_frames = len(tracking_data)
            skipped_frames = 0

            for frame_data in tracking_data:
                if all(
                    key in frame_data
                    for key in ["frame_number", "centroid_x", "centroid_y"]
                ):
                    # Skip frames with None values
                    if (frame_data["centroid_x"] is not None and
                        frame_data["centroid_y"] is not None):
                        frames.append(frame_data["frame_number"])
                        x_positions.append(frame_data["centroid_x"])
                        y_positions.append(frame_data["centroid_y"])
                    else:
                        skipped_frames += 1

            if not frames:
                status_callback("**Status:** ❌ No position data found", "#f8d7da")
                return

            # Inform about skipped frames if any
            if skipped_frames > 0:
                print(f"⚠️  Skipped {skipped_frames} frames with missing position data ({skipped_frames/total_frames*100:.1f}%)")

            # Calculate movement metrics
            x_positions = np.array(x_positions)
            y_positions = np.array(y_positions)

            # Calculate distances from center of mass
            center_x = np.mean(x_positions)
            center_y = np.mean(y_positions)
            distances_from_center = np.sqrt(
                (x_positions - center_x) ** 2 + (y_positions - center_y) ** 2
            )

            # Calculate velocity (frame-to-frame movement)
            velocities = []
            for i in range(1, len(x_positions)):
                dx = x_positions[i] - x_positions[i - 1]
                dy = y_positions[i] - y_positions[i - 1]
                velocity = np.sqrt(dx**2 + dy**2)
                velocities.append(velocity)

            base_name = Path(json_filename).stem

            if analysis_type == "individual":
                # Generate individual plots and save them separately
                self._generate_individual_plots(
                    x_positions,
                    y_positions,
                    frames,
                    velocities,
                    distances_from_center,
                    center_x,
                    center_y,
                    base_name,
                    export_format,
                    heatmap_bins,
                    heatmap_colormap,
                    heatmap_alpha,
                    movement_threshold_percentile,
                    velocity_bins,
                    status_callback,
                )
            else:
                # Generate complete panel
                self._generate_complete_panel(
                    x_positions,
                    y_positions,
                    frames,
                    velocities,
                    distances_from_center,
                    center_x,
                    center_y,
                    base_name,
                    export_format,
                    heatmap_bins,
                    heatmap_colormap,
                    heatmap_alpha,
                    movement_threshold_percentile,
                    velocity_bins,
                    status_callback,
                )

            # Cleanup temp file
            if temp_json_path.exists():
                temp_json_path.unlink()

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            status_callback(
                (
                    f"**Status:** ❌ Error generating analysis\n\n"
                    f"{str(e)}\n\n"
                    f"Details: {error_details[:200]}"
                ),
                "#f8d7da",
            )

    def _generate_complete_panel(
        self,
        x_positions: np.ndarray,
        y_positions: np.ndarray,
        frames: list[int],
        velocities: list[float],
        distances_from_center: np.ndarray,
        center_x: float,
        center_y: float,
        base_name: str,
        format_ext: str,
        heatmap_bins: int,
        heatmap_colormap: str,
        heatmap_alpha: float,
        movement_threshold_percentile: int,
        velocity_bins: int,
        status_callback: Callable[[str, str], None],
    ) -> None:
        """Generate complete analysis panel with all plots"""
        # Create comprehensive analysis figure
        fig = plt.figure(figsize=(24, 14))
        gs = fig.add_gridspec(2, 3, height_ratios=[2.5, 1.2], width_ratios=[1.5, 1, 1.5],
                             hspace=0.3, wspace=0.25)

        # Calculate additional statistics
        total_distance = np.sum(velocities) if velocities else 0
        max_distance_from_center = np.max(distances_from_center)
        movement_threshold = (
            np.percentile(velocities, movement_threshold_percentile)
            if velocities
            else 0
        )
        moving_frames = np.array(velocities) > movement_threshold if velocities else []
        stationary_ratio = (
            1 - (np.sum(moving_frames) / len(moving_frames))
            if len(moving_frames) > 0
            else 1
        )

        # Plot 1: High-resolution Movement Heatmap
        ax1 = fig.add_subplot(gs[0, :2])
        heatmap, _, _ = np.histogram2d(
            x_positions, y_positions, bins=heatmap_bins, density=True
        )
        heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=1.0)

        im = ax1.imshow(
            heatmap_smooth.T,
            origin="lower",
            extent=[
                min(x_positions),
                max(x_positions),
                min(y_positions),
                max(y_positions),
            ],
            cmap=heatmap_colormap,
            aspect="equal",
            alpha=heatmap_alpha,
            interpolation="bilinear",
        )

        ax1.plot(
            x_positions, y_positions, "k-", alpha=0.3, linewidth=0.5, label="Trajectory"
        )
        ax1.scatter(
            center_x,
            center_y,
            c="red",
            s=100,
            marker="x",
            linewidth=3,
            label="Center of Mass",
        )

        plt.colorbar(im, ax=ax1, label="Movement Density", shrink=0.6)
        ax1.set_title("Animal Movement Heatmap", fontsize=16, fontweight="bold")
        ax1.set_xlabel("X Position (pixels)", fontsize=12)
        ax1.set_ylabel("Y Position (pixels)", fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # Plot 2: Statistics Summary
        ax2 = fig.add_subplot(gs[0, 2])
        ax2.axis("off")
        ax2.set_title("Analysis Summary", fontsize=14, fontweight="bold", pad=10)

        stats_text = (
            f"Total Frames: {len(frames)}\n"
            f"Duration: {len(frames)} frames\n"
            "\n"
            f"Spatial Statistics:\n"
            f"• Center: ({center_x:.0f}, {center_y:.0f})\n"
            f"• Mean dist: {np.mean(distances_from_center):.1f}px\n"
            f"• Max dist: {max_distance_from_center:.1f}px\n"
            "\n"
            f"Movement Statistics:\n"
            f"• Total dist: {total_distance:.1f}px\n"
            f"• Mean vel: {np.mean(velocities) if velocities else 0:.2f}px/f\n"
            f"• Max vel: {np.max(velocities) if velocities else 0:.2f}px/f\n"
            f"• Threshold: {movement_threshold:.2f}px/f\n"
            f"• Stationary: {stationary_ratio*100:.1f}%\n"
            f"• Moving: {(1-stationary_ratio)*100:.1f}%\n"
            "\n"
            f"Configuration:\n"
            f"• Bins: {heatmap_bins}\n"
            f"• Colormap: {heatmap_colormap}\n"
            f"• Alpha: {heatmap_alpha}\n"
            f"• Threshold: {movement_threshold_percentile}th perc"
        )

        ax2.text(
            0.05,
            0.98,
            stats_text,
            transform=ax2.transAxes,
            fontsize=11,
            verticalalignment="top",
            fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="lightgray", alpha=0.9, pad=0.8),
            linespacing=1.2,
            wrap=True,
        )

        # Plot 3: Movement velocity
        ax3 = fig.add_subplot(gs[1, 0])
        if velocities:
            velocity_frames = frames[1:]
            ax3.plot(velocity_frames, velocities, "g-", linewidth=1, alpha=0.7)
            ax3.axhline(
                y=np.mean(velocities),
                color="r",
                linestyle="--",
                label=f"Mean: {np.mean(velocities):.1f}px/frame",
            )
            ax3.axhline(
                y=movement_threshold,
                color="orange",
                linestyle=":",
                label=f"Movement threshold",
            )
            ax3.set_title("Movement Velocity", fontsize=13, fontweight="bold")
            ax3.set_xlabel("Frame Number")
            ax3.set_ylabel("Velocity (pixels/frame)")
            ax3.grid(True, alpha=0.3)
            ax3.legend()

        # Plot 4: Velocity distribution
        ax4 = fig.add_subplot(gs[1, 1])
        if velocities:
            ax4.hist(
                velocities,
                bins=velocity_bins,
                alpha=0.7,
                color="purple",
                edgecolor="black",
            )
            ax4.axvline(
                x=np.mean(velocities),
                color="r",
                linestyle="--",
                label=f"Mean: {np.mean(velocities):.1f}px/frame",
            )
            ax4.axvline(
                x=movement_threshold,
                color="orange",
                linestyle=":",
                label=f"Movement threshold",
            )
            ax4.set_title("Velocity Distribution", fontsize=13, fontweight="bold")
            ax4.set_xlabel("Velocity (pixels/frame)")
            ax4.set_ylabel("Frequency")
            ax4.legend()

        # Plot 5: Activity classification
        ax5 = fig.add_subplot(gs[1, 2])
        if velocities:
            labels = ["Moving", "Stationary"]
            sizes = [1 - stationary_ratio, stationary_ratio]
            colors = ["#ff9999", "#66b3ff"]
            ax5.pie(
                sizes, labels=labels, autopct="%1.1f%%", colors=colors, startangle=90
            )
            ax5.set_title("Activity Classification", fontsize=13, fontweight="bold")

        plt.tight_layout(pad=2.0)

        # Save complete panel
        output_path = self.temp_dir / f"{base_name}_complete_analysis.{format_ext}"
        plt.savefig(
            output_path,
            format="eps" if format_ext == "eps" else "png",
            dpi=300,
            bbox_inches="tight",
        )

        plt.close()

        # Store path and enable download
        self.current_analysis_path = output_path

        # Export velocity data to JSON
        self._export_velocity_json(
            base_name,
            frames,
            x_positions,
            y_positions,
            velocities,
            distances_from_center,
            center_x,
            center_y,
            total_distance,
            movement_threshold,
            stationary_ratio,
        )

        # Success message
        file_size_kb = output_path.stat().st_size / 1024
        json_path = self.temp_dir / f"{base_name}_velocity.json"
        json_size_kb = json_path.stat().st_size / 1024 if json_path.exists() else 0

        success_msg = (
            "**Status:** ✅ Complete Analysis Generated\n\n"
            f"**Image File:** {output_path.name} ({file_size_kb:.1f} KB)\n\n"
            f"**JSON File:** {base_name}_velocity.json ({json_size_kb:.1f} KB)\n\n"
            "**Location:** ethological_tab/temp/\n\n"
            f"**Analysis Includes:**\n\n"
            f"• High-resolution movement heatmap\n\n"
            f"• Movement velocity analysis\n\n"
            f"• Velocity distribution histogram\n\n"
            f"• Activity classification\n\n"
            f"• Comprehensive statistics summary\n\n"
            f"• Velocity data JSON export\n\n"
            f"**Key Results:**\n\n"
            f"• Total distance: {total_distance:.1f}px\n\n"
            f"• Stationary time: {stationary_ratio*100:.1f}%\n\n"
            f"• Mean velocity: {np.mean(velocities) if velocities else 0:.1f}px/frame"
        )

        status_callback(success_msg, "#d4edda")

    def _generate_individual_plots(
        self,
        x_positions: np.ndarray,
        y_positions: np.ndarray,
        frames: list[int],
        velocities: list[float],
        distances_from_center: np.ndarray,
        center_x: float,
        center_y: float,
        base_name: str,
        format_ext: str,
        heatmap_bins: int,
        heatmap_colormap: str,
        heatmap_alpha: float,
        movement_threshold_percentile: int,
        velocity_bins: int,
        status_callback: Callable[[str, str], None],
    ) -> None:
        """Generate individual plots and save them separately"""
        dpi = 300
        plot_count = 0

        # Calculate statistics
        total_distance = np.sum(velocities) if velocities else 0
        movement_threshold = (
            np.percentile(velocities, movement_threshold_percentile)
            if velocities
            else 0
        )
        moving_frames = np.array(velocities) > movement_threshold if velocities else []
        stationary_ratio = (
            1 - (np.sum(moving_frames) / len(moving_frames))
            if len(moving_frames) > 0
            else 1
        )

        # 1. Heatmap
        plt.figure(figsize=(12, 8))
        heatmap, xedges, yedges = np.histogram2d(
            x_positions, y_positions, bins=heatmap_bins, density=True
        )
        heatmap_smooth = ndimage.gaussian_filter(heatmap, sigma=1.0)

        im = plt.imshow(
            heatmap_smooth.T,
            origin="lower",
            extent=[
                min(x_positions),
                max(x_positions),
                min(y_positions),
                max(y_positions),
            ],
            cmap=heatmap_colormap,
            aspect="equal",
            alpha=heatmap_alpha,
            interpolation="bilinear",
        )

        plt.plot(
            x_positions, y_positions, "k-", alpha=0.3, linewidth=0.5, label="Trajectory"
        )
        plt.scatter(
            center_x,
            center_y,
            c="red",
            s=100,
            marker="x",
            linewidth=3,
            label="Center of Mass",
        )

        plt.colorbar(im, label="Movement Density")
        plt.title("Animal Movement Heatmap", fontsize=16, fontweight="bold")
        plt.xlabel("X Position (pixels)", fontsize=12)
        plt.ylabel("Y Position (pixels)", fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend()

        output_path = self.temp_dir / f"{base_name}_01_heatmap.{format_ext}"
        plt.savefig(
            output_path,
            format="eps" if format_ext == "eps" else "png",
            dpi=dpi,
            bbox_inches="tight",
        )
        plt.close()
        plot_count += 1

        # Continue with other individual plots...
        if velocities:
            # 2. Movement velocity
            plt.figure(figsize=(10, 6))
            velocity_frames = frames[1:]
            plt.plot(velocity_frames, velocities, "g-", linewidth=1, alpha=0.7)
            plt.axhline(
                y=np.mean(velocities),
                color="r",
                linestyle="--",
                label=f"Mean: {np.mean(velocities):.1f}px/frame",
            )
            plt.axhline(
                y=movement_threshold,
                color="orange",
                linestyle=":",
                label=f"Movement threshold",
            )
            plt.title("Movement Velocity", fontsize=16, fontweight="bold")
            plt.xlabel("Frame Number")
            plt.ylabel("Velocity (pixels/frame)")
            plt.grid(True, alpha=0.3)
            plt.legend()

            output_path = self.temp_dir / f"{base_name}_02_velocity.{format_ext}"
            plt.savefig(
                output_path,
                format="eps" if format_ext == "eps" else "png",
                dpi=dpi,
                bbox_inches="tight",
            )
            plt.close()
            plot_count += 1

            # 3. Velocity distribution
            plt.figure(figsize=(8, 6))
            plt.hist(
                velocities,
                bins=velocity_bins,
                alpha=0.7,
                color="purple",
                edgecolor="black",
            )
            plt.axvline(
                x=np.mean(velocities),
                color="r",
                linestyle="--",
                label=f"Mean: {np.mean(velocities):.1f}px/frame",
            )
            plt.axvline(
                x=movement_threshold,
                color="orange",
                linestyle=":",
                label=f"Movement threshold",
            )
            plt.title("Velocity Distribution", fontsize=16, fontweight="bold")
            plt.xlabel("Velocity (pixels/frame)")
            plt.ylabel("Frequency")
            plt.legend()

            output_path = (
                self.temp_dir / f"{base_name}_03_velocity_distribution.{format_ext}"
            )

            plt.savefig(
                output_path,
                format="eps" if format_ext == "eps" else "png",
                dpi=dpi,
                bbox_inches="tight",
            )
            plt.close()
            plot_count += 1

            # 4. Activity classification
            plt.figure(figsize=(8, 8))
            labels = ["Moving", "Stationary"]
            sizes = [1 - stationary_ratio, stationary_ratio]
            colors = ["#ff9999", "#66b3ff"]
            plt.pie(
                sizes, labels=labels, autopct="%1.1f%%", colors=colors, startangle=90
            )
            plt.title("Activity Classification", fontsize=16, fontweight="bold")

            output_path = (
                self.temp_dir / f"{base_name}_04_activity_classification.{format_ext}"
            )
            plt.savefig(
                output_path,
                format="eps" if format_ext == "eps" else "png",
                dpi=dpi,
                bbox_inches="tight",
            )
            plt.close()
            plot_count += 1

        # Store the first path for download
        self.current_analysis_path = (
            self.temp_dir / f"{base_name}_01_heatmap.{format_ext}"
        )

        # Export velocity data to JSON
        self._export_velocity_json(
            base_name,
            frames,
            x_positions,
            y_positions,
            velocities,
            distances_from_center,
            center_x,
            center_y,
            total_distance,
            movement_threshold,
            stationary_ratio,
        )

        # Success message
        json_path = self.temp_dir / f"{base_name}_velocity.json"
        json_size_kb = json_path.stat().st_size / 1024 if json_path.exists() else 0

        success_msg = (
            "**Status:** ✅ Individual Plots Generated\n\n"
            f"**Files Generated:** {plot_count} individual plots\n\n"
            f"**JSON File:** {base_name}_velocity.json ({json_size_kb:.1f} KB)\n\n"
            f"**Location:** ethological_tab/temp/\n\n"
            f"**Format:** {format_ext.upper()}\n\n"
            f"**Plots Include:**\n\n"
            f"• {base_name}_01_heatmap.{format_ext}\n\n"
            f"• {base_name}_02_velocity.{format_ext}\n\n"
            f"• {base_name}_03_velocity_distribution.{format_ext}\n\n"
            f"• {base_name}_04_activity_classification.{format_ext}\n\n"
            f"**Data Export:**\n\n"
            f"• {base_name}_velocity.json (velocity data)\n\n"
            f"**Key Results:**\n\n"
            f"• Total distance: {total_distance:.1f}px\n\n"
            f"• Stationary time: {stationary_ratio*100:.1f}%\n\n"
            f"• Mean velocity: {np.mean(velocities) if velocities else 0:.1f}px/frame"
        )

        status_callback(success_msg, "#d4edda")

    def _export_velocity_json(
        self,
        base_name: str,
        frames: list[int],
        x_positions: np.ndarray,
        y_positions: np.ndarray,
        velocities: list[float],
        distances_from_center: np.ndarray,
        center_x: float,
        center_y: float,
        total_distance: float,
        movement_threshold: float,
        stationary_ratio: float,
    ) -> None:
        """Export velocity and movement data to JSON file"""
        try:
            # Prepare velocity data per frame
            velocity_data = []
            for i, frame in enumerate(frames):
                frame_data = {
                    "frame_number": int(frame),
                    "x_position": float(x_positions[i]),
                    "y_position": float(y_positions[i]),
                    "distance_from_center": float(distances_from_center[i]),
                }

                # Add velocity for frames after the first one
                if i > 0:
                    frame_data["velocity"] = float(velocities[i - 1])
                else:
                    frame_data["velocity"] = 0.0

                velocity_data.append(frame_data)

            # Prepare summary statistics
            summary = {
                "center_of_mass": {
                    "x": float(center_x),
                    "y": float(center_y),
                },
                "movement_statistics": {
                    "total_distance": float(total_distance),
                    "mean_velocity": float(np.mean(velocities)) if velocities else 0.0,
                    "max_velocity": float(np.max(velocities)) if velocities else 0.0,
                    "min_velocity": float(np.min(velocities)) if velocities else 0.0,
                    "std_velocity": float(np.std(velocities)) if velocities else 0.0,
                    "movement_threshold": float(movement_threshold),
                    "stationary_ratio": float(stationary_ratio),
                    "moving_ratio": float(1 - stationary_ratio),
                },
                "spatial_statistics": {
                    "mean_distance_from_center": float(np.mean(distances_from_center)),
                    "max_distance_from_center": float(np.max(distances_from_center)),
                    "std_distance_from_center": float(np.std(distances_from_center)),
                },
                "metadata": {
                    "total_frames": len(frames),
                    "source_file": base_name,
                }
            }

            # Combine data and summary
            output_data = {
                "summary": summary,
                "velocity_data": velocity_data,
            }

            # Save to JSON file with "_velocity" suffix
            json_output_path = self.temp_dir / f"{base_name}_velocity.json"
            with open(json_output_path, "w") as f:
                json.dump(output_data, f, indent=2)

            print(f"✅ Velocity data exported to: {json_output_path}")

        except Exception as e:
            print(f"❌ Error exporting velocity JSON: {e}")
            import traceback
            traceback.print_exc()

    def download_analysis_image(
        self, status_callback: Callable[[str, str], None]
    ) -> None:
        """Handle download button click for analysis images"""
        if not self.current_analysis_path or not self.current_analysis_path.exists():
            return

        try:

            with open(self.current_analysis_path, "rb") as f:
                image_data = f.read()

            # Create a data URL for download
            b64_data = base64.b64encode(image_data).decode()

            # Determine MIME type
            if self.current_analysis_path.suffix.lower() == ".eps":
                mime_type = "application/postscript"
            else:
                mime_type = "image/png"

            # Create download link
            js_code = (
                "const link = document.createElement('a');"
                f"link.href = 'data:{mime_type};base64,{b64_data}';"
                f"link.download = '{self.current_analysis_path.name}';"
                "document.body.appendChild(link);"
                "link.click();"
                "document.body.removeChild(link);"
            )

            # Execute JavaScript to trigger download
            pn.io.push_notebook()
            pn.pane.HTML(f"<script>{js_code}</script>").servable()

        except Exception as e:
            status_callback(
                f"**Status:** ❌ Download Error\n\nCould not download file: {str(e)}",
                "#f8d7da",
            )
