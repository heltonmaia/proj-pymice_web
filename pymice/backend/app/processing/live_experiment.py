"""Live experiment: capture, detect, record, emit events.

The loop runs in a daemon thread; it reads from the global
`camera_state["stream"]` (managed by app.routers.camera), so the user
must have started the stream before starting an experiment.

Artifacts written to temp/experiments/<exp_id>/:
  - raw.mp4         : raw frames from VideoWriter
  - tracking.jsonl  : one JSON per frame
  - events.jsonl    : one JSON per ROI/trigger/lifecycle event
  - metadata.json   : config + state
"""

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import cv2
import numpy as np

from app.models.schemas import ExperimentStartRequest, ROIPreset, TriggerRule
from app.processing.tracking import get_roi_containing_point, draw_rois
from app.processing.trigger_evaluator import TriggerEvaluator
from app.services.event_bus import EventBus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_yolo_model(model_path: str):
    """Indirected for testability."""
    from ultralytics import YOLO
    return YOLO(model_path)


def _best_detection(results) -> Optional[tuple]:
    """Pick the highest-confidence box from Ultralytics results.
    Returns (centroid_x, centroid_y, bbox_xyxy, confidence) or None.

    Handles both real Ultralytics Boxes (vectorised .conf / .xyxy tensors) and
    a list of individual box objects with scalar .conf / .xyxy attributes (used
    by the fake in tests).
    """
    if not results:
        return None
    r = results[0]
    boxes = getattr(r, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None

    # Real Ultralytics Boxes: vectorised .conf and .xyxy attributes
    if hasattr(boxes, "conf") and hasattr(boxes, "xyxy"):
        confs = boxes.conf
        if hasattr(confs, "cpu"):
            confs = confs.cpu().numpy()
        elif hasattr(confs, "numpy"):
            confs = confs.numpy()
        else:
            confs = np.asarray(confs)
        idx = int(np.argmax(confs))
        xyxy = boxes.xyxy
        if hasattr(xyxy, "cpu"):
            xyxy = xyxy.cpu().numpy()
        elif hasattr(xyxy, "numpy"):
            xyxy = xyxy.numpy()
        else:
            xyxy = np.asarray(xyxy)
        x1, y1, x2, y2 = xyxy[idx]
        return (
            int((x1 + x2) / 2),
            int((y1 + y2) / 2),
            [float(x1), float(y1), float(x2), float(y2)],
            float(confs[idx]),
        )

    # List of individual box objects (each with scalar .conf / .xyxy)
    best_box = None
    best_conf = -1.0
    for box in boxes:
        conf_val = float(np.asarray(box.conf).flat[0])
        if conf_val > best_conf:
            best_conf = conf_val
            best_box = box
    if best_box is None:
        return None
    xyxy = np.asarray(best_box.xyxy).flatten()
    x1, y1, x2, y2 = xyxy[:4]
    return (
        int((x1 + x2) / 2),
        int((y1 + y2) / 2),
        [float(x1), float(y1), float(x2), float(y2)],
        best_conf,
    )


@dataclass
class LiveExperimentArtifacts:
    exp_dir: str
    raw_video: str
    tracking_jsonl: str
    events_jsonl: str
    metadata_json: str


class LiveExperiment:
    def __init__(
        self,
        request: ExperimentStartRequest,
        event_bus: EventBus,
        stream_provider,
        annotated_frame_setter,
        action_dispatcher=None,
        base_dir: str = "temp/experiments",
    ):
        """
        stream_provider:           callable that returns the current cv2.VideoCapture or None
        annotated_frame_setter:    callable(np.ndarray) -> stores frame in shared buffer
        action_dispatcher:         callable(rule, event) -> result dict, or None for no-op
        """
        self.request = request
        self._bus = event_bus
        self._stream_provider = stream_provider
        self._annotated_frame_setter = annotated_frame_setter
        self._dispatch_action = action_dispatcher or (lambda rule, evt: {"ok": True, "skipped": "no_dispatcher"})
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rois_lock = threading.Lock()
        self._triggers_lock = threading.Lock()
        self._rois: List = list(request.rois.rois)
        self._roi_names: List[str] = [
            getattr(r, "name", f"roi_{i}") if False else f"roi_{i}"
            for i, r in enumerate(self._rois)
        ]
        self._evaluator = TriggerEvaluator(list(request.triggers))
        self._paused_roi_eval = False

        self.exp_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._artifacts = self._make_artifacts(base_dir)
        self._writer: Optional[cv2.VideoWriter] = None
        self._tracking_file = None
        self._events_file = None
        self._frames_processed = 0
        self._detections = 0
        self._events_emitted = 0
        self._last_active_roi: Optional[int] = None
        self._started_at_mono: Optional[float] = None
        self._started_at_iso: Optional[str] = None
        self._state = "idle"

    def _make_artifacts(self, base_dir: str) -> LiveExperimentArtifacts:
        exp_dir = os.path.join(base_dir, self.exp_id)
        os.makedirs(exp_dir, exist_ok=True)
        return LiveExperimentArtifacts(
            exp_dir=exp_dir,
            raw_video=os.path.join(exp_dir, "raw.mp4"),
            tracking_jsonl=os.path.join(exp_dir, "tracking.jsonl"),
            events_jsonl=os.path.join(exp_dir, "events.jsonl"),
            metadata_json=os.path.join(exp_dir, "metadata.json"),
        )

    # --- public lifecycle ---

    def start(self) -> None:
        cap = self._stream_provider()
        if cap is None:
            raise RuntimeError("No active camera stream")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_native = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fps_target = self.request.fps_target or fps_native

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(self._artifacts.raw_video, fourcc, fps_target, (width, height))
        if not self._writer.isOpened():
            raise RuntimeError("Failed to open VideoWriter")

        self._tracking_file = open(self._artifacts.tracking_jsonl, "w", buffering=1)
        self._events_file = open(self._artifacts.events_jsonl, "w", buffering=1)

        self._started_at_mono = time.monotonic()
        self._started_at_iso = _now_iso()
        self._state = "running"
        self._write_metadata()

        started = {
            "type": "started",
            "exp_id": self.exp_id,
            "started_at": self._started_at_iso,
        }
        self._emit(started)

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, reason: str = "user") -> None:
        if self._state != "running":
            return
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._state = "stopped"
        self._emit(
            {
                "type": "stopped",
                "frame_idx": self._frames_processed,
                "t": self._t_since_start(),
                "reason": reason,
            }
        )
        try:
            if self._writer is not None:
                self._writer.release()
        finally:
            self._writer = None
        for f in (self._tracking_file, self._events_file):
            try:
                if f is not None:
                    f.close()
            except Exception:
                pass
        self._write_metadata()

    # --- public mutators ---

    def update_rois(self, new_preset: ROIPreset) -> None:
        with self._rois_lock:
            self._rois = list(new_preset.rois)
            self._roi_names = [f"roi_{i}" for i, _ in enumerate(self._rois)]

    def set_paused_roi_eval(self, paused: bool) -> None:
        self._paused_roi_eval = paused

    def add_trigger(self, rule: TriggerRule) -> None:
        with self._triggers_lock:
            current = list(self._evaluator._rules)
            current.append(rule)
            self._evaluator.replace_rules(current)

    def remove_trigger(self, trigger_id: str) -> bool:
        with self._triggers_lock:
            current = [r for r in self._evaluator._rules if r.id != trigger_id]
            if len(current) == len(self._evaluator._rules):
                return False
            self._evaluator.replace_rules(current)
            return True

    def list_triggers(self) -> List[TriggerRule]:
        return list(self._evaluator._rules)

    # --- status ---

    def status(self) -> dict:
        return {
            "exp_id": self.exp_id,
            "state": self._state,
            "started_at": self._started_at_iso,
            "frames_processed": self._frames_processed,
            "fps_actual": self._fps_actual(),
            "detections": self._detections,
            "events_emitted": self._events_emitted,
            "last_active_roi": self._last_active_roi,
        }

    # --- internals ---

    def _t_since_start(self) -> float:
        if self._started_at_mono is None:
            return 0.0
        return time.monotonic() - self._started_at_mono

    def _fps_actual(self) -> float:
        elapsed = self._t_since_start()
        return self._frames_processed / elapsed if elapsed > 0 else 0.0

    def _emit(self, event: dict) -> None:
        self._events_emitted += 1
        self._bus.publish(event)
        if self._events_file is not None and not self._events_file.closed:
            self._events_file.write(json.dumps(event) + "\n")

    def _write_metadata(self) -> None:
        meta = {
            "exp_id": self.exp_id,
            "state": self._state,
            "started_at": self._started_at_iso,
            "config": {
                "device_id": self.request.device_id,
                "model_name": self.request.model_name,
                "rois": self.request.rois.model_dump(),
                "confidence_threshold": self.request.confidence_threshold,
                "iou_threshold": self.request.iou_threshold,
                "inference_size": self.request.inference_size,
                "fps_target": self.request.fps_target,
                "max_consecutive_drops": self.request.max_consecutive_drops,
            },
        }
        with open(self._artifacts.metadata_json, "w") as f:
            json.dump(meta, f, indent=2)

    def _loop(self) -> None:
        model_path = os.path.join("temp/models", self.request.model_name)
        if not os.path.exists(model_path):
            self._emit(
                {"type": "stopped", "frame_idx": 0, "t": 0.0, "reason": "model_missing"}
            )
            self._state = "stopped"
            return

        try:
            model = _load_yolo_model(model_path)
        except Exception as e:
            self._emit({"type": "stopped", "reason": f"model_load_error: {e}"})
            self._state = "stopped"
            return

        consecutive_drops = 0
        max_drops = self.request.max_consecutive_drops
        tick_interval = 1.0
        last_tick = 0.0

        while not self._stop_flag.is_set():
            cap = self._stream_provider()
            if cap is None:
                consecutive_drops += 1
                self._emit({"type": "frame_drop", "frame_idx": self._frames_processed})
                if consecutive_drops >= max_drops:
                    self._state = "stopped"
                    self._emit(
                        {"type": "stopped", "frame_idx": self._frames_processed,
                         "t": self._t_since_start(), "reason": "stream_lost"}
                    )
                    break
                time.sleep(0.05)
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                consecutive_drops += 1
                self._emit({"type": "frame_drop", "frame_idx": self._frames_processed})
                if consecutive_drops >= max_drops:
                    self._state = "stopped"
                    self._emit(
                        {"type": "stopped", "frame_idx": self._frames_processed,
                         "t": self._t_since_start(), "reason": "stream_lost"}
                    )
                    break
                time.sleep(0.01)
                continue
            consecutive_drops = 0

            frame_idx = self._frames_processed
            t = self._t_since_start()

            try:
                results = model.predict(
                    frame,
                    conf=self.request.confidence_threshold,
                    iou=self.request.iou_threshold,
                    imgsz=self.request.inference_size,
                    verbose=False,
                )
            except Exception as e:
                self._emit({"type": "stopped", "reason": f"detector_error: {e}"})
                self._state = "stopped"
                break

            detection = _best_detection(results)
            if detection is not None:
                cx, cy, bbox, conf = detection
                self._detections += 1
                centroid = (cx, cy)
            else:
                cx, cy, bbox, conf = None, None, None, None
                centroid = None

            active_roi: Optional[int] = None
            with self._rois_lock:
                rois = list(self._rois)
                roi_names = list(self._roi_names)
            if not self._paused_roi_eval and centroid is not None:
                active_roi = get_roi_containing_point(centroid, rois)

            events_this_frame: list = []
            if not self._paused_roi_eval and active_roi != self._last_active_roi:
                if self._last_active_roi is not None:
                    evt = {
                        "type": "roi_exit",
                        "frame_idx": frame_idx,
                        "t": t,
                        "roi_index": self._last_active_roi,
                        "roi_name": roi_names[self._last_active_roi]
                            if self._last_active_roi < len(roi_names) else None,
                    }
                    events_this_frame.append(evt)
                    self._emit(evt)
                if active_roi is not None:
                    evt = {
                        "type": "roi_entry",
                        "frame_idx": frame_idx,
                        "t": t,
                        "roi_index": active_roi,
                        "roi_name": roi_names[active_roi]
                            if active_roi < len(roi_names) else None,
                    }
                    events_this_frame.append(evt)
                    self._emit(evt)
                self._last_active_roi = active_roi

            with self._triggers_lock:
                fires = self._evaluator.evaluate(events_this_frame)
            for fire in fires:
                if fire.get("skipped"):
                    self._emit({"type": "trigger", **fire})
                    continue
                try:
                    result = self._dispatch_action(fire["rule"], fire)
                except Exception as e:
                    result = {"ok": False, "error": str(e)}
                self._emit(
                    {
                        "type": "trigger",
                        "trigger_id": fire["trigger_id"],
                        "frame_idx": fire["frame_idx"],
                        "t": fire["t"],
                        "result": result,
                    }
                )

            line = {
                "frame_idx": frame_idx,
                "t_capture_sec": t,
                "centroid_x": cx,
                "centroid_y": cy,
                "bbox": bbox,
                "confidence": conf,
                "active_roi": active_roi,
                "detection_method": "yolo" if detection else "none",
            }
            self._tracking_file.write(json.dumps(line) + "\n")

            self._writer.write(frame)
            annotated_frame = frame.copy()
            draw_rois(annotated_frame, rois, active_roi_index=active_roi)
            if centroid is not None:
                cv2.circle(annotated_frame, centroid, 4, (0, 0, 255), -1)
                if bbox is not None:
                    x1, y1, x2, y2 = (int(v) for v in bbox)
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            self._annotated_frame_setter(annotated_frame)

            self._frames_processed += 1

            if t - last_tick >= tick_interval:
                self._emit(
                    {
                        "type": "tick",
                        "frame_idx": frame_idx,
                        "t": t,
                        "fps_actual": self._fps_actual(),
                        "active_roi": active_roi,
                    }
                )
                last_tick = t
