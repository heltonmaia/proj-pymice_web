"""Integration test for the LiveExperiment loop.

VideoCapture and YOLO model are both replaced with fakes that produce
deterministic frames and detections. We assert on the on-disk artifacts.
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.models.schemas import (
    ExperimentStartRequest,
    RectangleROI,
    ROIPreset,
)
from app.processing.live_experiment import LiveExperiment
from app.services.event_bus import EventBus


class FakeCapture:
    def __init__(self, frames, width=320, height=240, fps=30.0):
        self._frames = frames
        self._i = 0
        self._w = width
        self._h = height
        self._fps = fps

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self._w
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self._h
        if prop == cv2.CAP_PROP_FPS:
            return self._fps
        return 0.0

    def read(self):
        if self._i >= len(self._frames):
            return False, None
        frame = self._frames[self._i]
        self._i += 1
        return True, frame


class FakeYOLO:
    """Returns a detection at (xs[i], ys[i]) for frame i."""

    def __init__(self, xs, ys):
        self._xs = xs
        self._ys = ys
        self._i = 0
        self.names = {0: "mouse"}

    def predict(self, frame, **kwargs):
        i = min(self._i, len(self._xs) - 1)
        x, y = self._xs[i], self._ys[i]
        self._i += 1

        class Box:
            def __init__(self, xyxy, conf, cls):
                self.xyxy = np.array([xyxy])
                self.conf = np.array([conf])
                self.cls = np.array([cls])

        class Result:
            def __init__(self, box):
                self.boxes = [box]

        bbox = (x - 5, y - 5, x + 5, y + 5)
        return [Result(Box(bbox, 0.9, 0))]


def _make_request():
    rois = ROIPreset(
        preset_name="t",
        description="",
        timestamp="2026-05-15",
        frame_width=320,
        frame_height=240,
        rois=[
            RectangleROI(
                roi_type="Rectangle",
                center_x=80, center_y=120, width=80, height=120,
            ),
            RectangleROI(
                roi_type="Rectangle",
                center_x=240, center_y=120, width=80, height=120,
            ),
        ],
    )
    return ExperimentStartRequest(
        device_id=0,
        model_name="dummy.pt",
        rois=rois,
        confidence_threshold=0.5,
        iou_threshold=0.5,
        max_consecutive_drops=3,
    )


@pytest.fixture
def in_tmp_workspace(tmp_path, monkeypatch):
    """Run tests in an isolated tmp_path with temp/models/dummy.pt created."""
    monkeypatch.chdir(tmp_path)
    models_dir = tmp_path / "temp" / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "dummy.pt").write_bytes(b"")  # empty placeholder; YOLO is patched
    return tmp_path


@pytest.mark.asyncio
async def test_loop_writes_tracking_and_roi_events(in_tmp_workspace):
    frames = [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(6)]
    xs = [50, 60, 240, 250, 60, 70]
    ys = [120, 120, 120, 120, 120, 120]

    bus = EventBus()
    fake_cap = FakeCapture(frames)
    annotated = {"frame": None}
    fake_model = FakeYOLO(xs, ys)

    with patch("app.processing.live_experiment._load_yolo_model", return_value=fake_model):
        exp = LiveExperiment(
            request=_make_request(),
            event_bus=bus,
            stream_provider=lambda: fake_cap,
            annotated_frame_setter=lambda f: annotated.__setitem__("frame", f),
            base_dir=str(in_tmp_workspace / "experiments"),
        )
        exp.start()
        time.sleep(2.0)
        exp.stop("test")

    tracking_lines = Path(exp._artifacts.tracking_jsonl).read_text().splitlines()
    events_lines = Path(exp._artifacts.events_jsonl).read_text().splitlines()

    assert len(tracking_lines) >= 6
    types = [json.loads(l).get("type") for l in events_lines]
    assert "started" in types
    assert types.count("roi_entry") >= 2
    assert types.count("roi_exit") >= 2
    assert "stopped" in types
    assert os.path.getsize(exp._artifacts.raw_video) > 0


@pytest.mark.asyncio
async def test_loop_auto_stops_on_consecutive_drops(in_tmp_workspace):
    frames = []
    bus = EventBus()
    fake_cap = FakeCapture(frames)
    annotated = {"frame": None}
    fake_model = FakeYOLO([0], [0])

    with patch("app.processing.live_experiment._load_yolo_model", return_value=fake_model):
        exp = LiveExperiment(
            request=_make_request(),
            event_bus=bus,
            stream_provider=lambda: fake_cap,
            annotated_frame_setter=lambda f: annotated.__setitem__("frame", f),
            base_dir=str(in_tmp_workspace / "experiments"),
        )
        exp.start()
        time.sleep(1.0)

    events = [json.loads(l) for l in Path(exp._artifacts.events_jsonl).read_text().splitlines()]
    stopped = [e for e in events if e.get("type") == "stopped"]
    assert stopped
    assert stopped[-1]["reason"] == "stream_lost"
