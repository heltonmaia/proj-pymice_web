"""Segmented recording for long sessions.

Two goals:
1. Cap each MP4 file at ~1 GB (configurable) so multi-hour recordings don't
   produce a single fragile file.
2. Decouple disk I/O from the detection loop via a writer thread, so YOLO
   inference and capture aren't blocked by VideoWriter.write() / file I/O.

Layout per experiment:
  <exp_dir>/raw_000.mp4
  <exp_dir>/raw_001.mp4
  <exp_dir>/tracking_000.jsonl
  <exp_dir>/tracking_001.jsonl
  <exp_dir>/events.jsonl     (not segmented; small)
  <exp_dir>/metadata.json    (carries the segments index)

Each (raw_NNN.mp4, tracking_NNN.jsonl) pair shares the same frame index range
so post-hoc analysis can align them by frame_idx.

The size check runs every N frames (default 100, ~3 s at 30 FPS) to keep
syscall overhead negligible. The duration cap is checked at the same cadence.
"""

import json
import os
import queue
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np


SIZE_CHECK_EVERY_N_FRAMES = 100


@dataclass
class SegmentInfo:
    index: int
    video: str
    tracking: str
    frame_start: int
    frame_end: Optional[int] = None
    started_at_sec: float = 0.0
    ended_at_sec: Optional[float] = None
    bytes: int = 0


class SegmentedRecorder:
    """Writes raw video + per-frame JSONL across rolling segments.

    Rotation triggers (whichever comes first):
      - segment file size >= max_bytes
      - elapsed time in segment >= max_seconds

    Both files in a segment rotate together so frame_idx ranges align.
    """

    def __init__(
        self,
        base_dir: str,
        max_bytes: int = 1_000_000_000,
        max_seconds: float = 1800.0,
        fps: float = 30.0,
        size: Tuple[int, int] = (640, 480),
        fourcc: str = "mp4v",
    ):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be > 0")
        if max_seconds <= 0:
            raise ValueError("max_seconds must be > 0")

        self.base_dir = base_dir
        self.max_bytes = max_bytes
        self.max_seconds = max_seconds
        self.fps = fps
        self.size = size
        self._fourcc = cv2.VideoWriter_fourcc(*fourcc)

        os.makedirs(base_dir, exist_ok=True)
        self._idx = 0
        self._writer: Optional[cv2.VideoWriter] = None
        self._tracking_file = None
        self._segments: List[SegmentInfo] = []
        self._open_segment(frame_start=0, t_start=0.0)

    # --- segment lifecycle ---

    def _video_path(self, idx: int) -> str:
        return os.path.join(self.base_dir, f"raw_{idx:03d}.mp4")

    def _tracking_path(self, idx: int) -> str:
        return os.path.join(self.base_dir, f"tracking_{idx:03d}.jsonl")

    def _open_segment(self, frame_start: int, t_start: float) -> None:
        path = self._video_path(self._idx)
        self._writer = cv2.VideoWriter(path, self._fourcc, self.fps, self.size)
        if not self._writer.isOpened():
            raise RuntimeError(f"Failed to open video segment {path}")
        self._tracking_file = open(self._tracking_path(self._idx), "w", buffering=1)
        self._segments.append(
            SegmentInfo(
                index=self._idx,
                video=os.path.basename(path),
                tracking=os.path.basename(self._tracking_path(self._idx)),
                frame_start=frame_start,
                started_at_sec=t_start,
            )
        )

    def _close_segment(self, frame_end: int, t_end: float) -> None:
        if self._segments:
            seg = self._segments[-1]
            seg.frame_end = frame_end
            seg.ended_at_sec = t_end
            try:
                seg.bytes = os.path.getsize(self._video_path(seg.index))
            except OSError:
                pass
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        if self._tracking_file is not None:
            self._tracking_file.close()
            self._tracking_file = None

    # --- main entry points ---

    def write(
        self,
        frame: np.ndarray,
        tracking_line: dict,
        frame_idx: int,
        t_now: float,
    ) -> Optional[int]:
        """Append a frame + tracking line. Returns new segment index on rotation, else None."""
        assert self._writer is not None and self._tracking_file is not None
        self._writer.write(frame)
        self._tracking_file.write(json.dumps(tracking_line) + "\n")

        if frame_idx == 0 or frame_idx % SIZE_CHECK_EVERY_N_FRAMES != 0:
            return None

        seg = self._segments[-1]
        try:
            size = os.path.getsize(self._video_path(seg.index))
            seg.bytes = size
        except OSError:
            size = 0

        elapsed = t_now - seg.started_at_sec
        if size < self.max_bytes and elapsed < self.max_seconds:
            return None

        # Rotate.
        self._close_segment(frame_end=frame_idx, t_end=t_now)
        self._idx += 1
        self._open_segment(frame_start=frame_idx + 1, t_start=t_now)
        return self._idx

    def release(self, final_frame_idx: int, final_t: float) -> None:
        self._close_segment(frame_end=final_frame_idx, t_end=final_t)

    # --- introspection ---

    def segments(self) -> List[dict]:
        return [
            {
                "index": s.index,
                "video": s.video,
                "tracking": s.tracking,
                "frame_start": s.frame_start,
                "frame_end": s.frame_end,
                "started_at_sec": s.started_at_sec,
                "ended_at_sec": s.ended_at_sec,
                "bytes": s.bytes,
            }
            for s in self._segments
        ]

    @property
    def current_index(self) -> int:
        return self._idx


class WriterThread(threading.Thread):
    """Background thread that drains (frame, tracking_line) pairs into a SegmentedRecorder.

    The detection loop submits non-blocking; if the queue is full, the loop is told
    via on_drop and the frame is discarded. This bounds the producer/consumer skew
    and gives the operator a visible signal when disk can't keep up.
    """

    def __init__(
        self,
        recorder: SegmentedRecorder,
        on_rotate: Callable[[int], None],
        on_drop: Callable[[int], None],
        max_queue: int = 300,
    ):
        super().__init__(daemon=True)
        self.recorder = recorder
        self.on_rotate = on_rotate
        self.on_drop = on_drop
        self._q: "queue.Queue[Tuple[np.ndarray, dict, int, float]]" = queue.Queue(maxsize=max_queue)
        self._stop_evt = threading.Event()

    def submit(self, frame: np.ndarray, line: dict, frame_idx: int, t: float) -> bool:
        try:
            self._q.put_nowait((frame, line, frame_idx, t))
            return True
        except queue.Full:
            self.on_drop(frame_idx)
            return False

    def run(self) -> None:
        while not self._stop_evt.is_set() or not self._q.empty():
            try:
                frame, line, frame_idx, t = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            new_idx = self.recorder.write(frame, line, frame_idx, t)
            if new_idx is not None:
                try:
                    self.on_rotate(new_idx)
                except Exception:
                    pass  # don't kill the writer on emit errors

    def stop(self, final_frame_idx: int, final_t: float, timeout: float = 10.0) -> None:
        self._stop_evt.set()
        self.join(timeout=timeout)
        self.recorder.release(final_frame_idx, final_t)

    @property
    def queue_depth(self) -> int:
        return self._q.qsize()
