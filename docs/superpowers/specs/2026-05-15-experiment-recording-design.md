# Experiment Recording — design

**Status:** approved (brainstorm), pending implementation plan
**Date:** 2026-05-15
**Scope:** v1 — YOLO live tracking + ROI overlay + recording + hardware-trigger seam

## Goal

Replace the current **Camera** tab with **Experiment Recording**: a single surface where the user attaches a camera, draws ROIs, runs YOLO tracking live, records the raw video and per-frame tracking JSON, and fires triggers to Arduino/ESP32 (or HTTP endpoints) when ROI events match user-defined rules. SAM3 and pose estimation are out of v1; the architecture leaves seams for them.

## Decisions locked during brainstorm

| Question | Decision |
|---|---|
| Scope of v1 | YOLO + ROI live + recording. SAM3/pose deferred. |
| Tab | Rename Camera → Experiment Recording (single tab, no sub-tabs). |
| ROI UI reuse | Extract `<ROICanvas>` shared component; refactor TrackingTab to consume it. |
| Persistence | Raw video **and** tracking JSONL in parallel, same loop, same frame_idx. |
| Closed-loop seam | WebSocket event channel + declarative trigger registry, in v1. |
| Loop ownership | Backend-driven loop reading `camera_state["stream"]`, frontend consumes via existing frame-polling + WebSocket. |
| Hardware | Native `serial` (Arduino/ESP32 USB) and `http` (ESP32 WiFi/LAN) integrations. MQTT deferred. |
| Frontend tests | None new — Vitest not in repo; manual check covers v1. |

## Architecture

### Frontend

- `pages/ExperimentRecordingTab.tsx` — replaces `CameraTab.tsx` (rename, keep all current stream/recording features). Three view states: **Setup**, **Live**, **Done**.
- `components/ROICanvas.tsx` — new shared component. Props: `{ width, height, rois, onRoisChange, mode: 'edit' | 'view-only' | 'live-overlay', activeRoiIndex?, backgroundFrame? }`. Tool state (Rectangle/Circle/Polygon/OpenField*) is internal; ROIs are controlled by parent. Drawing logic extracted verbatim from current TrackingTab.
- `pages/TrackingTab.tsx` — refactored to consume `<ROICanvas>` instead of inline canvas logic. Same behavior, smaller file.
- `services/api.ts` — gains `experimentApi` (`start`, `stop`, `status`, `listIntegrations`, `createIntegration`, `deleteIntegration`, `testIntegration`, `listSerialPorts`, `listTriggers`, `createTrigger`, `deleteTrigger`, `updateRois`, `subscribeEvents` WebSocket helper).

Display reuses `/api/camera/frame` polling unchanged. During Live, the backend writes the annotated frame back into a shared buffer that `/api/camera/frame` prefers when present — so no new display endpoint, no canvas refactor.

### Backend

- `app/routers/experiment.py` — new, mounted at `/api/experiment`. REST endpoints + `WS /events`.
- `app/processing/live_experiment.py` — new. `LiveExperiment` class owns the capture/detect/write/publish loop in a daemon thread.
- `app/services/event_bus.py` — new (finally justifies the empty `services/` dir). In-process pub/sub backed by per-subscriber `asyncio.Queue(maxsize=1024)`.
- `app/services/integrations.py` — new. `SerialAdapter`, `HttpAdapter`, registry persisted to `temp/integrations.json`.
- `app/models/schemas.py` — adds `ExperimentStartRequest`, `ExperimentStatus`, `Integration`, `TriggerRule`, `ExperimentEvent`.
- `app/routers/camera.py` — minor: `/frame` checks for `camera_state["annotated_frame"]` first and serves it during a live experiment.
- `app/main.py` — `cleanup_temp_directories` excludes `temp/experiments/` and `temp/integrations.json` (don't wipe user data on restart). Startup also scans for orphan experiments and marks them `crashed`.
- `pyproject.toml` — adds `pyserial`.

### Artifacts per experiment

```
temp/experiments/<exp_id>/
  raw.mp4              # raw frames from VideoWriter (no overlay)
  tracking.jsonl       # one JSON per frame
  events.jsonl         # one JSON per ROI/trigger/lifecycle event
  metadata.json        # config + state ("running" | "stopped" | "crashed")
```

`<exp_id>` = `exp_<YYYYMMDD_HHMMSS>_<6 char random>`.

### Singleton model

One `LiveExperiment` per process. `EXPERIMENT_STATE = {"current": Optional[LiveExperiment]}`. `POST /start` → 409 if `current` is running. `POST /stop` → 404 if no current experiment.

## Components — detail

### `LiveExperiment` (backend)

Constructor: `(device_id, model_name, rois, fps_target, triggers, output_dir)`.

Public API:
- `start()` — creates artifacts dir, opens VideoWriter + JSONL files, spawns daemon thread.
- `stop(reason: str = "user")` — sets flag, joins thread, flushes/closes files, emits `stopped` event.
- `update_rois(new_rois)` — atomic swap under `rois_lock`. Next frame uses new ROIs.
- `add_trigger(rule) / remove_trigger(trigger_id)` — atomic under `triggers_lock`. Active from next frame.
- `status() -> dict` — `{state, started_at, frames_processed, fps_actual, detections, events_emitted}`.

Loop body (`_loop`):
1. `ret, frame = camera_state["stream"].read()` — on `False`, emit `frame_drop`, increment consecutive-fail counter, `stop("stream_lost")` after 30 (configurable).
2. `t_capture = now - started_at` (monotonic seconds).
3. `detection = _detect_yolo(frame, model)` — reuses helper extracted from `processing/tracking.py`.
4. Under `rois_lock`: `active = _evaluate_roi(detection.centroid, rois)`.
5. Compute ROI deltas (entry/exit) vs `last_active`. Emit each event.
6. `_evaluate_triggers(events_this_frame)` — match rules under `triggers_lock`, fire actions via `asyncio.create_task` (so disk write is not blocked by hardware).
7. Annotate frame (bbox + centroid + active ROI label); write **raw frame** to `VideoWriter`; update `camera_state["annotated_frame"]` for `/api/camera/frame`.
8. Append line to `tracking.jsonl`.
9. Emit `tick` event at 1Hz.
10. Loop back; if processing took >1/fps_target, the next `cap.read()` skips ahead — frame drops are recorded.

### `EventBus`

```python
class EventBus:
    async def subscribe(self) -> AsyncIterator[dict]: ...
    def publish(self, event: dict) -> None: ...
```

`publish` is sync (called from the loop thread). Each subscriber has a queue; full queue → subscriber dropped (WS closes with 1011). `events.jsonl` is always written regardless of subscribers.

### Integrations

```python
@dataclass
class Integration:
    id: str
    name: str
    kind: Literal["serial", "http"]
    config: dict  # kind-specific
```

`SerialAdapter`:
- Holds `serial.Serial(port, baud)` open for the integration's lifetime.
- `write(payload: str | bytes)` runs in executor; appends `newline` for serial mode.
- Reopens on next call if the port raised `SerialException`.

`HttpAdapter`:
- Holds `httpx.AsyncClient(base_url=..., headers=..., timeout=...)`.
- `send(payload)` → `POST` with JSON body (or raw string).
- Whitelist: `localhost`, `127.0.0.1`, RFC1918 ranges (`10/8`, `172.16/12`, `192.168/16`). External hosts → 400 at create time.

Registry persisted as JSON list in `temp/integrations.json`. Survives restarts and is excluded from `cleanup_temp_directories`.

### Triggers

```json
{
  "id": "t-1",
  "name": "Feed on center entry",
  "match": {
    "event_type": "roi_entry",
    "roi_name": "center",
    "min_dwell_sec": 0.5,
    "cooldown_sec": 10
  },
  "action": {
    "integration_id": "i-arduino-1",
    "payload": "DROP",
    "timeout_sec": 2
  }
}
```

Per-trigger state held by `LiveExperiment`: `last_fired_at`, `entry_t_per_roi`. Cooldown counts from fire time (not response). Suppressed fires still emit `{type: "trigger", trigger_id, result: {skipped: "cooldown"}}` for visibility in `events.jsonl` and WS.

**Lifetime:** Triggers belong to the current `LiveExperiment` and are **not persisted** across experiments — the user creates them as part of starting an experiment (`ExperimentStartRequest.triggers`) or while it runs (`POST /api/experiment/triggers`). They die with `stop`. Integrations, in contrast, persist in `temp/integrations.json`. Rationale: triggers are session-specific scientific configuration; integrations are hardware bindings.

Special action `{kind: "log", label: "..."}` requires no integration; writes a labeled marker to `events.jsonl`. Useful for visual annotations without hardware.

## Data flow

### Setup → Live

```
[Frontend]                              [Backend]
GET /api/camera/devices              →
POST /api/camera/stream/start        →  camera_state["stream"] = cv2.VideoCapture(id)
GET /api/camera/frame (33ms poll)    →  (raw frame)
(user draws ROIs, picks model)
POST /api/experiment/start           →  LiveExperiment(...).start()
                                          create temp/experiments/<exp_id>/
                                          open VideoWriter, jsonl files
                                          spawn daemon → _loop()
                                     ←  200 {exp_id, ws_url}
WS /api/experiment/events            ←  {type: "started", exp_id, started_at}
GET /api/camera/frame                →  (annotated frame from shared buffer)
```

### Loop emits (illustrative)

```
{"type": "started",     "exp_id": "exp_...", "started_at": "2026-05-15T18:00:00Z"}
{"type": "roi_entry",   "frame_idx": 142, "t": 4.733, "roi_index": 0, "roi_name": "center"}
{"type": "roi_exit",    "frame_idx": 281, "t": 9.367, "roi_index": 0, "roi_name": "center"}
{"type": "trigger",     "frame_idx": 142, "t": 4.733, "trigger_id": "t-1", "result": {"status_code": 200, "latency_ms": 38}}
{"type": "trigger",     "frame_idx": 145, "t": 4.833, "trigger_id": "t-1", "result": {"skipped": "cooldown"}}
{"type": "integration_error", "integration_id": "i-arduino-1", "error": "serial port closed"}
{"type": "frame_drop",  "frame_idx": 305}
{"type": "tick",        "frame_idx": 600, "t": 20.0, "fps_actual": 29.8, "active_roi": null}
{"type": "stopped",     "frame_idx": 1800, "t": 60.0, "reason": "user"}
```

All events except `started` carry `frame_idx` and `t` (seconds since `started_at`).

### Live → Stop

```
POST /api/experiment/stop            →  LiveExperiment.stop("user")
                                          flag → loop completes current frame
                                          flush jsonls, close VideoWriter
                                          emit {type: "stopped"}, write metadata.json {state: "stopped"}
                                     ←  200 {exp_id, artifacts: [...]}
WS                                   ←  server closes
```

### ROI edits during Live

UI "Edit ROIs" toggle puts `ROICanvas` in `mode='edit'` over the current annotated frame; backend's `paused_roi_eval` flag pauses entry/exit emission (ticks continue, video recording continues). Confirm → `POST /api/experiment/rois` → `LiveExperiment.update_rois()`. New ROIs apply on next frame; `paused_roi_eval` lifts.

## Error handling (summary; see brainstorm transcript for full reasoning)

| Failure | Behavior |
|---|---|
| Stream not started before `/experiment/start` | 409 with "No active stream" |
| `cap.read()` returns False | Emit `frame_drop`; auto-stop after N consecutive (`ExperimentStartRequest.max_consecutive_drops`, default 30) |
| Camera unplugged | Same as above; no auto-reconnect in v1 |
| Model file missing | 400 at `/start` with list of available models |
| CUDA OOM | Emit `stopped` reason `cuda_oom`; no CPU fallback |
| Detector slower than capture | Frames serial; backlog → frame drops. `fps_actual` reports it |
| Disk I/O error mid-loop | Emit `stopped` reason `io_error`; preserve partial artifacts |
| Webhook timeout / 5xx | `trigger.result.error`, loop continues, cooldown still ticks |
| Serial disconnect | `integration_error`, status red, reopen on next action |
| Action queue saturated | Per-integration `Semaphore(8)`; excess → `result: {error: "queue_full"}` |
| WS subscriber slow | Drop with close 1011; `events.jsonl` is the canonical record |
| Frontend tab close | Backend keeps running; on reload, toast: Resume / Stop / Download |
| Backend restart mid-experiment | Mark orphan `crashed` in `metadata.json`; no resume in v1 |
| `POST /camera/stream/stop` during experiment | Hits `stream_lost`; frontend disables that button during Live |

## Testing

No new automated frontend tests (Vitest not in repo; introducing it is out of scope).

### Backend pytest (new — `pymice/backend/tests/`)

1. `test_event_bus.py` — publish to N subscribers; slow subscriber overflow → disconnect; unsubscribe cleanup.
2. `test_trigger_evaluator.py` — synthetic event sequences exercise `min_dwell_sec`, `cooldown_sec`, `roi_name` filter, multi-trigger same-frame.
3. `test_live_experiment_loop.py` — `cv2.VideoCapture` mocked; verifies `tracking.jsonl`/`events.jsonl` correctness on a scripted mouse trajectory; verifies `frame_drop` and `stream_lost` paths; YOLO mocked (this is not a detector test).
4. `test_integration_serial.py` — `pyserial.tools.list_ports` + `serial.Serial` mocked; test signal, reopen-on-error, disconnect during write.
5. `test_integration_http.py` — `httpx.MockTransport`; whitelist enforcement, LAN allowed, public host blocked, 5xx surfaces in result.

Optional (not blocking merge): `test_router_experiment.py` with `TestClient` for status codes (409 on double start, 404 on stop without experiment, schema contracts).

### Manual check (mandatory before PR)

12-step golden path + 2 failure cases. Listed in full in the brainstorm transcript; summarized here as the checklist:

1. Backend up, navigate to Experiment Recording.
2. Stream from device 0.
3. Add Integration (invalid URL) — error surfaces correctly.
4. Add valid Integration (HTTP to `nc -l 9000` or real Arduino).
5. Draw a Rectangle + Circle ROI.
6. Trigger 1: `roi_entry` ROI 0 → `log` action.
7. Trigger 2: `roi_entry` ROI 1 → integration action.
8. Select YOLO model, Start Experiment, induce ROI crossings.
9. Verify all 4 artifacts in `temp/experiments/<exp_id>/`; verify external endpoint received POST.
10. Stop; download all 4 artifacts.
11. Unplug camera mid-experiment — `stopped reason: stream_lost`, partial artifacts preserved.
12. Cooldown test: two entries within `cooldown_sec` — second is silenced with `skipped: cooldown` event.

### Definition of done

- pytest passes
- 12-step manual check passes
- `npm run build` typechecks clean
- `npm run lint` zero warnings
- `CLAUDE.md` updated: new `/api/experiment` line in API surface; Domain notes line for the live pipeline + integrations
- `docs/diferenciais.md` updated to reflect the live-experiment capability

## Explicit non-goals (v1)

- SAM3 segmentation in live mode
- Pose estimation (any model)
- Template-matching fallback in live loop
- Resume of crashed experiments
- CUDA→CPU fallback
- Automatic camera reconnection
- Disk-space monitoring
- MQTT/OSC/GPIO integrations
- Replay buffer for late WebSocket subscribers
- Authentication on WebSocket / REST (matches existing project posture)

These are individually viable and architecturally non-conflicting — defer without prejudice.
