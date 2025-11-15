import json
from pathlib import Path
from typing import Optional


class FileHandler:
    """Handles file operations and validation for ethological analysis"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.experiments_dir = project_root / "experiments"

    def validate_json_file(self, json_path: Path) -> bool:
        """Validate that JSON file contains tracking data"""
        try:
            with open(json_path, "r") as f:
                data = json.load(f)

            # Check for required structure
            if not isinstance(data, dict):
                return False

            # Check for tracking_data field
            tracking_data = data.get("tracking_data", [])
            if not isinstance(tracking_data, list):
                return False

            # If there's data, check first frame structure
            if len(tracking_data) > 0:
                first_frame = tracking_data[0]
                required_fields = ["frame_number", "centroid_x", "centroid_y"]
                for field in required_fields:
                    if field not in first_frame:
                        return False

            return True

        except (json.JSONDecodeError, FileNotFoundError, KeyError):
            return False

    def find_json_by_name(self, video_stem: str) -> Optional[Path]:
        """Find corresponding JSON file by video name in experiments directory"""
        if not self.experiments_dir.exists():
            return None

        # Pattern 1: tracking_data_<video_name>_<timestamp>.json
        for json_file in self.experiments_dir.rglob(
            f"tracking_data_{video_stem}*.json"
        ):
            return json_file

        # Pattern 2: <video_name>.json
        for json_file in self.experiments_dir.rglob(f"{video_stem}.json"):
            return json_file

        # Pattern 3: Look for any JSON file with video stem in name
        for json_file in self.experiments_dir.rglob("*.json"):
            if video_stem in json_file.stem:
                return json_file

        return None

    def validate_uploaded_json(self, json_value: bytes, temp_path: Path) -> bool:
        """Validate uploaded JSON data by creating temp file and checking it"""
        try:
            with open(temp_path, "wb") as f:
                f.write(json_value)

            is_valid = self.validate_json_file(temp_path)

            # Cleanup temp file
            if temp_path.exists():
                temp_path.unlink()

            return is_valid

        except Exception:
            # Cleanup temp file on error
            if temp_path.exists():
                temp_path.unlink()
            return False
