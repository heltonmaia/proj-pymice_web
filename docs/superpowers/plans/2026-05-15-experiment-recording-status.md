# Experiment Recording — execution status

**Branch:** `feat/experiment-recording`
**Base:** `main` at `8ce9a89` (docs commit)
**State:** all 17 implementation tasks committed; backend fully verified; interactive UI/hardware check remains for the user.

## Completed (18 of 18 tasks)

| # | Task | Commit | Tests |
|---|---|---|---|
| T1 | Schemas + deps (pyserial/httpx) | `3fac7ac` + `70b4932` | n/a |
| T2 | pytest scaffolding | `ae5d27b` | 0 collected |
| T3 | EventBus pub/sub | `4842996` | 3/3 |
| T4 | TriggerEvaluator (cooldown + dwell) | `61f2676` | 5/5 |
| T5 | Integrations (Serial + HTTP + LAN whitelist) | `6f67f55` | 5/5 |
| T6 | LiveExperiment skeleton | `dab1cb6` | n/a |
| T7 | LiveExperiment loop body | `fe4004f` | 2/2 |
| T8 | Pluggable action dispatcher | `34f7178` | re-runs T7 (2/2) |
| T9 | Camera `/frame` annotated buffer | `8317d55` | n/a |
| T10 | `/api/experiment` router (REST + WS) | `f4b0997` | n/a |
| T11 | main.py wiring + orphan detection | `254acde` | n/a |
| T12 | Frontend types + experimentApi + Vite WS proxy | `d22ac71` | n/a |
| T13 | ROICanvas shared component (TrackingTab refactor deferred) | `1a48039` | n/a |
| T14 | ExperimentRecordingTab replaces CameraTab | `400c98a` | n/a |
| T15 | IntegrationsPanel UI | `479d032` | n/a |
| T16 | TriggersPanel UI | `9f71012` | n/a |
| T17 | Docs (CLAUDE.md + diferenciais.md) | `65c6fc0` | n/a |
| T18 | Manual check (partial — see below) | — | 15/15 pytest |

**18 commits, +764 / −7 lines initially, plus the full frontend + router additions.**

## Verified automatically (T18)

```bash
source uv-env/bin/activate
cd pymice/backend
pytest tests/ -v
# → 15 passed in 5.49s
```

Backend boot + endpoint smoke (with `python -m uvicorn app.main:app --port 8765`):

- `GET /health` → `{"status":"healthy"}`
- `GET /api/experiment/status` → `{"success":true,"data":{"state":"idle"},"error":null}`
- `GET /api/experiment/integrations` → empty list
- `GET /api/experiment/triggers` → empty list (no running experiment)
- `GET /api/experiment/serial-ports` → enumerates `/dev/ttyS*`

Frontend `npm run build`: zero NEW TS errors introduced by feature code. 17 pre-existing errors remain in `App.tsx`, `EthologicalTab.tsx`, `ExtraToolsTab.tsx`, `TrackingTab.tsx`, `VisualizarResultadosTab.tsx`, `canvas.ts` — pre-date this feature, intentionally left untouched per branching decision.

## Remaining for user (interactive T18)

These steps need a browser + camera + (optionally) hardware:

1. `./pymice/run.sh start` (activate venv first).
2. Open `http://localhost:5765` → Experiment Recording tab.
3. Start Stream on a USB camera → frame appears.
4. (Optional) Add Integration (HTTP `http://localhost:9000` pointing to `nc -lk 9000` listener); click Test → green dot.
5. Draw two ROIs (Rectangle + Circle).
6. Pick a YOLO model from the dropdown.
7. Start Experiment → annotated bbox/circle appear; Event Log fills with `roi_entry/exit` as object crosses ROIs.
8. (Optional) Add Trigger: `roi_entry`, ROI 1, integration target, payload `DROP` → verify `nc` receives POST when entering ROI 1.
9. Two entries within `cooldown_sec` → second emits `skipped: cooldown` in Event Log.
10. Stop Experiment → Done view; download `raw.mp4`, `tracking.jsonl`, `events.jsonl`, `metadata.json` from `temp/experiments/<exp_id>/`.
11. (Failure path) Unplug camera mid-experiment → `stopped reason: stream_lost`, partial artifacts preserved.

## Deferred / known follow-ups

- **TrackingTab refactor to use `ROICanvas`** (originally part of T13) — deferred to keep delivery low-risk on a 1983-line file. `ROICanvas` exists and is used by ExperimentRecordingTab; TrackingTab continues with its inline implementation. Tracking tab still works as before.
- **Pre-existing TS errors** (17, in 6 unrelated files) — leave alone per branching decision.
- **MQTT/OSC/GPIO integrations** — roadmap (per spec).
- **Pose estimation, SAM3 live, template-matching fallback in live loop** — roadmap.

## How to ship

```bash
git push -u origin feat/experiment-recording
# then open PR against main referencing docs/superpowers/specs/2026-05-15-experiment-recording-design.md
```

Branch is local-only — no push has happened.
