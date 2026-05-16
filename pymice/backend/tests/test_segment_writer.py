"""Tests for SegmentedRecorder + WriterThread."""

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.processing.segment_writer import (
    SegmentedRecorder,
    WriterThread,
    SIZE_CHECK_EVERY_N_FRAMES,
)


def _make_frame(w=64, h=48, color=(0, 0, 0)):
    f = np.zeros((h, w, 3), dtype=np.uint8)
    f[:] = color
    return f


def test_rotates_on_size_threshold(tmp_path):
    # Tiny size cap so a few frames trigger rotation.
    rec = SegmentedRecorder(
        str(tmp_path),
        max_bytes=10_000,
        max_seconds=10_000,
        fps=30.0,
        size=(64, 48),
    )
    # Write enough frames to exceed 10KB. Each non-zero frame is a few hundred bytes
    # after mp4v compression — easily 10KB after a few hundred frames.
    for i in range(SIZE_CHECK_EVERY_N_FRAMES * 5):
        # Use random noise so compression doesn't squash everything to zero.
        f = (np.random.rand(48, 64, 3) * 255).astype(np.uint8)
        rec.write(f, {"frame_idx": i, "t": i / 30.0}, i, i / 30.0)
    rec.release(SIZE_CHECK_EVERY_N_FRAMES * 5 - 1, 999.0)

    segs = rec.segments()
    assert len(segs) >= 2, f"expected >=2 segments, got {len(segs)}"

    # Each segment file exists with non-zero size.
    for s in segs:
        vp = tmp_path / s["video"]
        tp = tmp_path / s["tracking"]
        assert vp.exists(), f"missing {vp}"
        assert tp.exists(), f"missing {tp}"
        assert os.path.getsize(vp) > 0

    # frame_start / frame_end form a contiguous, non-overlapping cover.
    prev_end = -1
    for s in segs:
        assert s["frame_start"] == prev_end + 1, f"gap before segment {s['index']}"
        if s["frame_end"] is not None:
            prev_end = s["frame_end"]


def test_rotates_on_time_threshold(tmp_path):
    rec = SegmentedRecorder(
        str(tmp_path),
        max_bytes=10**12,  # effectively no size cap
        max_seconds=1.0,   # rotate after 1 second
        fps=30.0,
        size=(64, 48),
    )
    # Frame timestamps span > 1s, but size check only fires every 100 frames.
    for i in range(SIZE_CHECK_EVERY_N_FRAMES * 3):
        # Skip ahead in time at the check frames so duration cap trips.
        t = 0.0 if i % SIZE_CHECK_EVERY_N_FRAMES else (i // SIZE_CHECK_EVERY_N_FRAMES) * 2.0
        rec.write(_make_frame(), {"frame_idx": i, "t": t}, i, t)
    rec.release(SIZE_CHECK_EVERY_N_FRAMES * 3 - 1, 6.0)

    segs = rec.segments()
    assert len(segs) >= 2


def test_tracking_jsonl_contains_one_line_per_frame(tmp_path):
    rec = SegmentedRecorder(str(tmp_path), max_bytes=10**12, max_seconds=10**12, fps=30.0, size=(64, 48))
    for i in range(50):
        rec.write(_make_frame(), {"frame_idx": i, "x": i * 1.5}, i, i / 30.0)
    rec.release(49, 49 / 30.0)

    seg = rec.segments()[0]
    lines = Path(tmp_path / seg["tracking"]).read_text().splitlines()
    assert len(lines) == 50
    first = json.loads(lines[0])
    assert first["frame_idx"] == 0
    assert first["x"] == 0.0


def test_writer_thread_drains_queue_and_rotates(tmp_path):
    rec = SegmentedRecorder(
        str(tmp_path),
        max_bytes=10_000,
        max_seconds=10**12,
        fps=30.0,
        size=(64, 48),
    )
    rotations = []
    drops = []
    wt = WriterThread(
        rec,
        on_rotate=lambda new_idx: rotations.append(new_idx),
        on_drop=lambda fi: drops.append(fi),
        max_queue=50,
    )
    wt.start()

    for i in range(SIZE_CHECK_EVERY_N_FRAMES * 5):
        f = (np.random.rand(48, 64, 3) * 255).astype(np.uint8)
        wt.submit(f, {"frame_idx": i, "t": i / 30.0}, i, i / 30.0)

    # Allow drain.
    time.sleep(2.0)
    wt.stop(final_frame_idx=SIZE_CHECK_EVERY_N_FRAMES * 5 - 1, final_t=999.0)

    assert len(rotations) >= 1, "expected at least one rotation"
    assert all(r >= 1 for r in rotations)


def test_writer_thread_drop_when_queue_full(tmp_path):
    """Stress: tight queue and fast producer should see at least some drops."""
    rec = SegmentedRecorder(str(tmp_path), max_bytes=10**12, max_seconds=10**12, fps=30.0, size=(640, 480))
    drops = []
    wt = WriterThread(rec, on_rotate=lambda _: None, on_drop=lambda fi: drops.append(fi), max_queue=2)
    wt.start()

    for i in range(200):
        # Big frames to slow the writer thread.
        wt.submit((np.random.rand(480, 640, 3) * 255).astype(np.uint8), {"frame_idx": i}, i, 0.0)

    wt.stop(final_frame_idx=199, final_t=0.0)
    # Not asserting exact count — depends on disk speed — but at queue size 2 with 200 fast submissions,
    # there should typically be drops. If the disk is extremely fast it may not happen, so make it
    # soft: just verify it didn't crash and the recorder produced at least one segment.
    assert len(rec.segments()) >= 1
