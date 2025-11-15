#!/usr/bin/env python3
"""
Video Visualization Tool for Tracking Data

This script generates a new video with tracking visualizations overlaid on the original video.
It reads tracking data from JSON files and renders:
- Mouse detection centroids (YOLO and Template matching)
- ROIs (rectangles, circles, polygons)
- Frame statistics and information

Usage:
    python testVideo_json.py input_video.mp4 tracking_data.json [output_video.mp4]

Example:
    python testVideo_json.py mouse_experiment.mp4 tracking_data_mouse_experiment_20250827.json output_with_tracking.mp4
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import cv2 as cv
import numpy as np

# Color definitions (matching the tracking system)
COLORS = {
    "mask": (255, 165, 0),  # Orange (YOLO detection)
    "centroid": (0, 255, 255),  # Yellow (YOLO centroid)
    "template_mask": (0, 255, 0),  # Green (Template detection)
    "template_centroid": (255, 0, 255),  # Purple (Template centroid)
    "text": (255, 255, 255),  # White
    "roi_rectangle": (255, 0, 255),  # Magenta
    "roi_circle": (0, 255, 0),  # Green
    "roi_polygon": (100, 0, 0),  # Dark red
    "trail": (128, 128, 255),  # Light blue for trail
    "info_bg": (0, 0, 0),  # Black background for info panel
}

FONT = cv.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.6
THICKNESS = 2


class TrackingVisualizer:
    def __init__(
        self,
        video_path: str,
        json_path: str,
        output_path: Optional[str] = None,
        show_info: bool = False,
        show_heatmap: bool = True,
        progress_callback=None,
    ) -> None:
        self.video_path = Path(video_path)
        self.json_path = Path(json_path)
        self.show_info = show_info
        self.show_heatmap = show_heatmap
        self.progress_callback = progress_callback

        if output_path:
            self.output_path = Path(output_path)
        else:
            # Generate output filename based on input video
            stem = self.video_path.stem
            suffix = self.video_path.suffix
            self.output_path = (
                self.video_path.parent / f"{stem}_tracking_visualized{suffix}"
            )

        # Load tracking data
        with open(self.json_path, "r") as f:
            self.tracking_data = json.load(f)

        # Initialize video capture
        self.cap = cv.VideoCapture(str(self.video_path))
        if not self.cap.isOpened():
            raise ValueError(f"Cannot open video file: {self.video_path}")

        # Get video properties
        self.fps = int(self.cap.get(cv.CAP_PROP_FPS))
        self.frame_width = int(self.cap.get(cv.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.cap.get(cv.CAP_PROP_FRAME_COUNT))

        print(
            f"Video properties:\n"
            f"  Resolution: {self.frame_width}x{self.frame_height}\n"
            f"  FPS: {self.fps}\n"
            f"  Total frames: {self.total_frames}"
        )

        # Initialize video writer
        fourcc = cv.VideoWriter_fourcc(*"mp4v")
        self.writer = cv.VideoWriter(
            str(self.output_path),
            fourcc,
            self.fps,
            (self.frame_width, self.frame_height),
        )

        # Create centroid trail for visualization
        self.centroid_trail = []
        self.max_trail_length = 150  # Number of points to keep in trail (longer trail)

        # Create mini-map for accumulated trajectory (30% smaller and proportional)
        self.mini_map_base_size = 140  # Base size reduced by 30% (200 * 0.7)
        self.mini_map_margin = 10  # Margin from edge
        self.accumulated_trail = []  # Stores all centroids for the mini-map

        # Calculate proportional mini-map dimensions to match video aspect ratio
        aspect_ratio = self.frame_width / self.frame_height

        if aspect_ratio >= 1:  # Landscape or square
            self.mini_map_width = self.mini_map_base_size
            self.mini_map_height = int(self.mini_map_base_size / aspect_ratio)
        else:  # Portrait
            self.mini_map_height = self.mini_map_base_size
            self.mini_map_width = int(self.mini_map_base_size * aspect_ratio)

        # Scale factors for mini-map (maintain aspect ratio)
        self.scale_x = self.mini_map_width / self.frame_width
        self.scale_y = self.mini_map_height / self.frame_height

        # Heat map data structure for tracking visit frequency
        self.heat_map = np.zeros(
            (self.mini_map_height, self.mini_map_width), dtype=np.float32
        )

    def convert_roi_format(self, rois: list[dict]) -> list[dict]:
        """Convert ROI format from JSON tracking data to draw_rois format"""
        converted_rois = []
        
        for roi in rois:
            roi_type = roi.get("roi_type", "").lower()
            
            if roi_type == "rectangle":
                # Convert from center/width/height to x0,y0,x1,y1
                center_x = roi.get("center_x", 0)
                center_y = roi.get("center_y", 0)
                width = roi.get("width", 0)
                height = roi.get("height", 0)
                
                # Handle negative width/height by calculating correct corners
                if width < 0:
                    x0 = center_x + width // 2  # width is negative, so this subtracts
                    x1 = center_x - width // 2  # width is negative, so this adds
                else:
                    x0 = center_x - width // 2
                    x1 = center_x + width // 2
                    
                if height < 0:
                    y0 = center_y + height // 2  # height is negative, so this subtracts  
                    y1 = center_y - height // 2  # height is negative, so this adds
                else:
                    y0 = center_y - height // 2
                    y1 = center_y + height // 2
                
                converted_rois.append({
                    "type": "rectangle",
                    "coordinates": [x0, y0, x1, y1]
                })
                
            elif roi_type == "circle":
                # Convert from center/radius format
                center_x = roi.get("center_x", 0)
                center_y = roi.get("center_y", 0)
                radius = roi.get("radius", 0)
                
                converted_rois.append({
                    "type": "circle",
                    "coordinates": [center_x, center_y, radius]
                })
                
            elif roi_type == "polygon":
                # Convert vertices format
                vertices = roi.get("vertices", [])
                if vertices:
                    converted_rois.append({
                        "type": "polygon",
                        "coordinates": vertices
                    })
        
        return converted_rois

    def draw_rois(self, frame: np.ndarray, rois: list[dict]) -> np.ndarray:
        """Draw ROIs on the frame"""
        for roi in rois:
            roi_type = roi.get("type", "unknown")

            if roi_type == "rectangle":
                x0, y0, x1, y1 = roi["coordinates"]
                cv.rectangle(
                    frame,
                    (int(x0), int(y0)),
                    (int(x1), int(y1)),
                    COLORS["roi_rectangle"],
                    2,
                )

            elif roi_type == "circle":
                center_x, center_y, radius = roi["coordinates"]
                cv.circle(
                    frame,
                    (int(center_x), int(center_y)),
                    int(radius),
                    COLORS["roi_circle"],
                    2,
                )
                overlay = frame.copy()
                cv.circle(
                    overlay,
                    (int(center_x), int(center_y)),
                    int(radius),
                    COLORS["roi_circle"],
                    -1,
                )
                cv.addWeighted(overlay, 0.1, frame, 0.9, 0, frame)

            elif roi_type == "polygon":
                points = np.array(roi["coordinates"], np.int32)
                points = points.reshape((-1, 1, 2))
                cv.polylines(frame, [points], True, COLORS["roi_polygon"], 2)

        return frame

    def draw_centroid(
        self, frame: np.ndarray, x: int, y: int, detection_method: str
    ) -> np.ndarray:
        """Draw centroid on the frame"""
        if detection_method == "YOLO":
            color = COLORS["centroid"]
            # Draw smaller circle for YOLO detection
            cv.circle(frame, (x, y), 3, color, -1)
            cv.circle(frame, (x, y), 5, color, 1)
        elif detection_method == "Template":
            color = COLORS["template_centroid"]
            # Draw smaller shape for template detection
            cv.circle(frame, (x, y), 5, color, 1)
            cv.circle(frame, (x, y), 2, color, -1)

        return frame

    def draw_trail(self, frame: np.ndarray) -> np.ndarray:
        """Draw centroid trail"""
        if len(self.centroid_trail) < 2:
            return frame

        # Draw trail lines with fading effect
        for i in range(1, len(self.centroid_trail)):
            alpha = i / len(self.centroid_trail)  # Fade effect
            thickness = max(1, int(3 * alpha))

            pt1 = self.centroid_trail[i - 1]
            pt2 = self.centroid_trail[i]

            # Create faded color
            color = tuple(int(c * alpha) for c in COLORS["trail"])
            cv.line(frame, pt1, pt2, color, thickness)

        return frame

    def draw_info_panel(
        self, frame: np.ndarray, frame_data: dict, frame_num: int
    ) -> np.ndarray:
        """Draw compact information panel on the frame (top-left corner when heatmap is enabled)"""
        # Panel dimensions (smaller)
        panel_width = 200
        panel_height = 80

        # Position based on whether heatmap is shown
        if self.show_heatmap:
            # Position in top-left corner to avoid heatmap
            panel_x = 10
            panel_y = 10
        else:
            # Position in top-right corner
            panel_x = self.frame_width - panel_width - 10
            panel_y = 10

        # Create semi-transparent background for info panel
        overlay = frame.copy()
        cv.rectangle(
            overlay,
            (panel_x, panel_y),
            (panel_x + panel_width, panel_y + panel_height),
            COLORS["info_bg"],
            -1,
        )
        cv.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

        # Draw border
        cv.rectangle(
            frame,
            (panel_x, panel_y),
            (panel_x + panel_width, panel_y + panel_height),
            COLORS["text"],
            1,
        )

        # Display information (smaller font and compact layout)
        font_scale = 0.4
        y_offset = panel_y + 15
        line_height = 15
        text_x = panel_x + 5

        # Frame information
        cv.putText(
            frame,
            f"Frame: {frame_num}/{self.total_frames}",
            (text_x, y_offset),
            FONT,
            font_scale,
            COLORS["text"],
            1,
        )
        y_offset += line_height

        # Detection method
        detection_method = frame_data.get("detection_method", "None")
        cv.putText(
            frame,
            f"Method: {detection_method}",
            (text_x, y_offset),
            FONT,
            font_scale,
            COLORS["text"],
            1,
        )
        y_offset += line_height

        # Centroid coordinates (abbreviated)
        centroid_x = frame_data.get("centroid_x")
        centroid_y = frame_data.get("centroid_y")
        if centroid_x is not None and centroid_y is not None:
            cv.putText(
                frame,
                f"XY: ({centroid_x}, {centroid_y})",
                (text_x, y_offset),
                FONT,
                font_scale,
                COLORS["text"],
                1,
            )
        else:
            cv.putText(
                frame,
                "XY: No detection",
                (text_x, y_offset),
                FONT,
                font_scale,
                COLORS["text"],
                1,
            )
        y_offset += line_height

        # Overall statistics (compact)
        total_yolo = self.tracking_data.get("yolo_detections", 0)
        total_template = self.tracking_data.get("template_detections", 0)
        cv.putText(
            frame,
            f"Y:{total_yolo} T:{total_template}",
            (text_x, y_offset),
            FONT,
            font_scale,
            COLORS["text"],
            1,
        )

        return frame

    def update_heat_map(self, centroid_x: int, centroid_y: int) -> None:
        """Update heat map with current position"""
        # Convert to mini-map coordinates
        map_x = int(centroid_x * self.scale_x)
        map_y = int(centroid_y * self.scale_y)

        # Ensure coordinates are within bounds
        map_x = max(0, min(map_x, self.mini_map_width - 1))
        map_y = max(0, min(map_y, self.mini_map_height - 1))

        # Add heat to current position and surrounding area (Gaussian-like distribution)
        radius = 3  # Heat spread radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                heat_x = map_x + dx
                heat_y = map_y + dy

                # Check bounds
                if (
                    0 <= heat_x < self.mini_map_width
                    and 0 <= heat_y < self.mini_map_height
                ):
                    # Calculate distance from center
                    distance = np.sqrt(dx * dx + dy * dy)
                    if distance <= radius:
                        # Gaussian-like heat distribution (higher at center)
                        heat_intensity = np.exp(
                            -(distance**2) / (2 * (radius / 2) ** 2)
                        )
                        self.heat_map[heat_y, heat_x] += heat_intensity

    def draw_mini_map(self, frame: np.ndarray) -> np.ndarray:
        """Draw accumulated trajectory heat map in top-right corner"""
        if len(self.accumulated_trail) < 2:
            return frame

        # Calculate mini-map position (top-right corner)
        mini_x = self.frame_width - self.mini_map_width - self.mini_map_margin
        mini_y = self.mini_map_margin

        # Create mini-map region
        mini_map_region = np.zeros(
            (self.mini_map_height, self.mini_map_width, 3), dtype=np.uint8
        )

        # Normalize heat map for visualization
        if np.max(self.heat_map) > 0:
            normalized_heat = (self.heat_map / np.max(self.heat_map) * 255).astype(
                np.uint8
            )

            # Apply colormap to heat map (create heat map colors)
            for y in range(self.mini_map_height):
                for x in range(self.mini_map_width):
                    heat_value = normalized_heat[y, x]
                    if heat_value > 0:
                        # Create heat map colors: blue (cold) -> green -> yellow -> red (hot)
                        if heat_value < 64:  # Cold (blue to cyan)
                            r = 0
                            g = heat_value * 4
                            b = 255
                        elif heat_value < 128:  # Warm (cyan to yellow)
                            r = (heat_value - 64) * 4
                            g = 255
                            b = 255 - (heat_value - 64) * 4
                        elif heat_value < 192:  # Hot (yellow to orange)
                            r = 255
                            g = 255 - (heat_value - 128) * 2
                            b = 0
                        else:  # Very hot (orange to red)
                            r = 255
                            g = max(0, 127 - (heat_value - 192) * 2)
                            b = 0

                        mini_map_region[y, x] = [b, g, r]  # BGR format for OpenCV

        # Blend heat map with frame
        overlay = frame.copy()

        # Place mini-map on frame
        overlay[
            mini_y : mini_y + self.mini_map_height,
            mini_x : mini_x + self.mini_map_width,
        ] = mini_map_region

        # Blend with original frame
        cv.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # Draw border
        cv.rectangle(
            frame,
            (mini_x - 2, mini_y - 2),
            (mini_x + self.mini_map_width + 2, mini_y + self.mini_map_height + 2),
            COLORS["text"],
            1,
        )

        # Draw current position if we have recent data
        if len(self.accumulated_trail) > 0:
            curr_x, curr_y = self.accumulated_trail[-1]
            map_x = int(mini_x + curr_x * self.scale_x)
            map_y = int(mini_y + curr_y * self.scale_y)

            # Ensure current position is within bounds
            map_x = max(mini_x, min(map_x, mini_x + self.mini_map_width - 1))
            map_y = max(mini_y, min(map_y, mini_y + self.mini_map_height - 1))

            # Highlight current position with white circle
            cv.circle(frame, (map_x, map_y), 2, (255, 255, 255), -1)
            cv.circle(frame, (map_x, map_y), 3, (0, 0, 0), 1)

        # Add mini-map label
        cv.putText(
            frame, "Heat Map", (mini_x, mini_y - 10), FONT, 0.35, COLORS["text"], 1
        )

        return frame

    def process_video(self) -> None:
        """Process the entire video and generate output with visualizations"""
        print(
            f"Processing video: {self.video_path}\n"
            f"Using tracking data: {self.json_path}\n"
            f"Output will be saved to: {self.output_path}\n"
        )

        frame_num = 0
        tracking_frames = self.tracking_data.get("tracking_data", [])
        rois = self.tracking_data.get("rois", [])
        
        # Convert ROIs to proper format for drawing
        converted_rois = self.convert_roi_format(rois) if rois else []

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            # Convert BGR to RGB for processing (OpenCV uses BGR)
            frame_rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)

            # Get tracking data for current frame
            frame_data = None
            for track_frame in tracking_frames:
                if track_frame.get("frame_number") == frame_num:
                    frame_data = track_frame
                    break

            if frame_data is None:
                frame_data = {"detection_method": "No data"}

            # Draw ROIs
            if converted_rois:
                frame_rgb = self.draw_rois(frame_rgb, converted_rois)

            # Draw centroid and update trail
            centroid_x = frame_data.get("centroid_x")
            centroid_y = frame_data.get("centroid_y")
            detection_method = frame_data.get("detection_method", "None")

            if centroid_x is not None and centroid_y is not None:
                # Add to temporary trail (for main video)
                self.centroid_trail.append((int(centroid_x), int(centroid_y)))
                if len(self.centroid_trail) > self.max_trail_length:
                    self.centroid_trail.pop(0)

                # Add to accumulated trail (for mini-map - never removed)
                self.accumulated_trail.append((int(centroid_x), int(centroid_y)))

                # Update heat map (if enabled)
                if self.show_heatmap:
                    self.update_heat_map(int(centroid_x), int(centroid_y))

                # Draw centroid
                frame_rgb = self.draw_centroid(
                    frame_rgb, int(centroid_x), int(centroid_y), detection_method
                )

            # Draw trail
            frame_rgb = self.draw_trail(frame_rgb)

            # Draw mini-map with accumulated trajectory (if enabled)
            if self.show_heatmap:
                frame_rgb = self.draw_mini_map(frame_rgb)

            # Draw information panel (only if requested)
            if self.show_info:
                frame_rgb = self.draw_info_panel(frame_rgb, frame_data, frame_num)

            # Convert back to BGR for video writer
            frame_bgr = cv.cvtColor(frame_rgb, cv.COLOR_RGB2BGR)

            # Write frame to output video
            self.writer.write(frame_bgr)

            frame_num += 1

            # Progress indicator
            if frame_num % 100 == 0:
                progress = (frame_num / self.total_frames) * 100
                print(
                    f"Progress: {progress:.1f}% ({frame_num}/{self.total_frames} frames)"
                )
                # Update UI progress bar if callback is provided
                if self.progress_callback:
                    ui_progress = 30 + int(progress * 0.65)  # Map to 30-95% range
                    self.progress_callback(ui_progress)

        print(
            f"Video processing completed!\n"
            f"Processed {frame_num} frames\n"
            f"Output saved to: {self.output_path}"
        )

    def cleanup(self) -> None:
        """Release resources"""
        if self.cap:
            self.cap.release()
        if self.writer:
            self.writer.release()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate video with tracking visualizations",
        epilog="Example: python testVideo_json.py video.mp4 tracking_data.json output.mp4",
    )

    parser.add_argument("video_path", help="Path to input video file")
    parser.add_argument("json_path", help="Path to tracking data JSON file")
    parser.add_argument(
        "output_path", nargs="?", help="Path to output video file (optional)"
    )
    parser.add_argument(
        "--show-info", action="store_true", help="Show information panel on video"
    )
    parser.add_argument(
        "--show-heatmap",
        action="store_true",
        default=True,
        help="Show heat map on video (default: True)",
    )

    args = parser.parse_args()

    # Validate input files
    if not Path(args.video_path).exists():
        print(f"Error: Video file not found: {args.video_path}")
        sys.exit(1)

    if not Path(args.json_path).exists():
        print(f"Error: JSON file not found: {args.json_path}")
        sys.exit(1)

    try:
        # Create visualizer and process video
        visualizer = TrackingVisualizer(
            args.video_path,
            args.json_path,
            args.output_path,
            args.show_info,
            args.show_heatmap,
        )
        visualizer.process_video()
        visualizer.cleanup()

        print("\nVisualization completed successfully!")

    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
