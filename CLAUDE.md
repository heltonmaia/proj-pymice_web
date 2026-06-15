# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
- **Name:** proj-pymice_web (PyMice Web)
- **Purpose:** Web application for mouse tracking and behavioral/ethological analysis (Open Field, heatmaps, trajectories, ROI-based metrics).
- **Architecture:** Monorepo under `pymice/` with a FastAPI backend and a React + TypeScript frontend.

## Stack
- **Frontend:** React 18 + TypeScript, Vite, TailwindCSS, Axios, Lucide React, React Query (provider mounted at root; per-page state is local `useState`), React-Konva (interactive ROI drawing), Recharts. Note: `zustand` is in `package.json` but currently unused — `frontend/src/store/` is empty.
- **Backend:** Python 3.11, FastAPI, Pydantic, PyTorch 2.6.0 (CUDA 12.4), Ultralytics 8.3.102 (YOLO), OpenCV, ffmpeg/ffprobe. Optional SAM3 support (see Domain notes).
- **Python packaging:** `uv` (always — do not use pip/poetry/conda for this repo). `pymice/backend/requirements.txt` is kept only as a fallback/reference; `pyproject.toml` + `uv.lock` are the source of truth. The ML stack is **optional extras**, not core deps: `gpu` (torch/torchvision/torchaudio 2.6.0), `yolo` (ultralytics), `dev` (pytest/black/isort/flake8). A from-scratch install needs `uv pip install -e '.[gpu,yolo,dev]'` from `pymice/backend/` — the shared `uv-env` already has them.

## Layout
```
proj-pymice_web/
├── pymice/
│   ├── backend/          # FastAPI app
│   │   └── app/
│   │       ├── main.py        # Entry point + startup cleanup
│   │       ├── routers/       # camera, video, tracking, roi, analysis, system, experiment
│   │       ├── models/        # Pydantic schemas
│   │       ├── processing/    # detection.py, tracking.py, live_experiment.py,
│   │       │                  #   segment_writer.py, trigger_evaluator.py
│   │       └── services/      # event_bus.py, integrations.py
│   ├── frontend/         # React app
│   │   └── src/
│   │       ├── App.tsx        # Tab shell (locks tabs during tracking)
│   │       ├── pages/         # One per tab: TrackingTab, EthologicalTab,
│   │       │                  #   ExperimentRecordingTab, ExtraToolsTab, IRLTab,
│   │       │                  #   SyntheticTab, VisualizarResultadosTab
│   │       ├── services/api.ts # Axios client, all backend endpoints
│   │       └── components, hooks, types, utils
│   ├── logs/             # Runtime logs (backend.log, frontend.log, *.pid)
│   ├── run.py            # Unified cross-platform start/stop/status script (stdlib)
│   └── setup_backend.sh  # Backend environment setup
├── docs/                 # Project positioning notes (diferenciais.md + .tex/PDF build, in PT-BR)
├── uv-env  → /mnt/hd3/uv-common/pymice-react-venv   (symlink to UV virtualenv)
├── .venv   → same target as uv-env
└── README.md
```

## Environment
- **UV venv:** `uv-env/` (symlink → `/mnt/hd3/uv-common/pymice-react-venv`; venv dir kept under its historical name). Activate with `source uv-env/bin/activate` from repo root, or `source ../uv-env/bin/activate` from `pymice/backend/`.
- **UV cache:** `/mnt/hd3/uv-common/uv-web`.
- **GPU check:** `python -c "import torch; print(torch.cuda.is_available())"`.

## Running
- Preferred: `python pymice/run.py start` (also: `status`, `stop`, `restart`, `clean`, `logs [backend|frontend]`, `update`, or run with no args for interactive menu). `run.py` is stdlib-only and resolves every path from its own location, so it runs from any CWD. It is the single cross-platform entry point (the old `run.sh`/`run.bat` were removed).
- **`run.py` locates the venv itself** — it searches `uv-env`/`.venv` (repo root, then `pymice/`) and `$PYMICE_VENV`, then launches the backend via that venv's `python -m uvicorn`. No `source .../activate` needed; invoke it with the system Python. (It deliberately uses `python -m uvicorn`, not the venv's `uvicorn` console-script, whose shebang is stale from a prior venv path and fails to exec.)
- `run.py start` also runs its `clean()` step and the backend `startup_event` clears `temp/{videos,tracking,analysis,roi_templates}` (files >1h old) — anything you stage there for debugging may be wiped on next start. **Preserved across restarts:** `temp/models/*.pt`, `temp/experiments/` (user recordings), and `temp/integrations.json` (hardware bindings). On startup, `_mark_orphan_experiments()` also rewrites any `temp/experiments/*/metadata.json` whose `state == "running"` to `"crashed"` (covers a previous run that died mid-experiment).
- **Camera lifecycle:** the cv2 capture in `camera_state["stream"]` is shared with the experiment loop. A daemon watchdog (`start_watchdog` in `app/routers/camera.py`) releases the cap if no `/api/camera/frame` request arrives for ~30s — this catches "user closed the tab" so the camera LED stops staying on. On SIGTERM/SIGINT, shutdown order is **experiment → camera → watchdog** (the loop reads the camera, so it must stop first); preserve this ordering if you touch `app/main.py`'s `shutdown_event`.
- Ports: Frontend dev http://localhost:5765 — Backend http://localhost:8765 — Docs http://localhost:8765/docs.
- Vite proxies `/api/*` → `http://localhost:8765` (see `frontend/vite.config.ts`); the frontend axios client uses `baseURL: '/api'`, so both dev and prod talk to the same paths.
- Logs: `tail -f pymice/logs/*.log`.

## Commands
- **Backend dev server (manual):** from `pymice/backend/`, `uvicorn app.main:app --reload --host 0.0.0.0 --port 8765`.
- **Frontend (from `pymice/frontend/`):**
  - `npm run dev` — Vite dev server on 5765.
  - `npm run build` — runs `tsc --noEmit` (type-check only, no JS emit) then `vite build` to `dist/`. Use this to verify TS before commits.
  - `npm run lint` — ESLint with `--max-warnings 0` (zero-warning policy).
  - `npm run preview` — preview the built bundle.
- **Backend formatting/lint:** dev extras provide `black` (line-length 100), `isort` (black profile), `flake8`, `pytest`. Install with `uv pip install -e '.[dev]'`.
- **Backend tests:** a real suite now lives under `pymice/backend/tests/` (`test_event_bus.py`, `test_integration_http.py`, `test_integration_serial.py`, `test_live_experiment_loop.py`, `test_segment_writer.py`, `test_trigger_evaluator.py`) covering the experiment-recording stack. Run with `pytest` from `pymice/backend/` (asyncio_mode=auto is set in `pyproject.toml`); run a single file with `pytest tests/test_live_experiment_loop.py` or a single test with `pytest tests/test_live_experiment_loop.py::test_name`. The standalone scripts at the backend root (`test_cuda.py`, `test_sam3.py`, `test_outlier_filter.py`) are probes — run them directly with `python <file>`, not via pytest.

## API surface
Routers are mounted in `app/main.py`:
- `/api/camera` — device list, live stream, recording.
- `/api/video` — upload, info, frame, download, list.
- `/api/tracking` — YOLO models, start/stop/progress, results, ROI templates, test-detection, batch prepare.
- `/api/roi` — named ROI presets.
- `/api/analysis` — heatmap, movement, complete analysis, Open Field, video export, large-JSON upload/load.
- `/api/system` — GPU check, YOLO benchmark.
- `/api/experiment` — live tracking (start/stop/status), Arduino/ESP32 integrations CRUD, trigger rules, WebSocket `/events`, artifact download.

CORS is hard-coded to `http://localhost:3000` and `http://localhost:5765` — update `app/main.py` if you change the frontend port.

## Conventions
- Keep environment setup reproducible — any new Python dependency goes through `uv` and is reflected in `pyproject.toml` / `uv.lock`.
- Frontend styling: Tailwind utility classes; dark mode is class-based (`dark:` variants throughout) and toggled via `components/ThemeToggle.tsx` + `hooks/useTheme.ts`. Avoid ad-hoc CSS unless necessary.
- Frontend path alias: `@/` → `src/` (set in `vite.config.ts` and `tsconfig.json`). Use it for cross-tree imports.
- Backend: follow FastAPI conventions (routers in `app/routers`, Pydantic schemas in `app/models`, processing/CV/ML logic in `app/processing`, cross-router runtime services in `app/services` — currently `event_bus.py` and `integrations.py`). `app/utils` exists but is empty; put pure helpers there rather than inline in routers.
- `run.py` resolves its own paths, so it runs from any CWD — but the backend still resolves `temp/` relative to `pymice/backend/`, so be mindful of CWD when launching the backend manually (e.g. `uvicorn`).

## Domain notes
- **Heatmap:** **Power Normalization** with gamma=0.4 to expand low-density regions; colorbar is normalized 0–1. Don't switch to linear without a reason — it makes low-traffic areas invisible next to hotspots.
- **Ethological analysis (`EthologicalTab.tsx` + `app/routers/analysis.py`):** primary surface for post-tracking metrics — Velocity and Activity cards live side-by-side here. Velocity uses a **Median + k·MAD** outlier filter; when MAD collapses to zero on quantized/zero-inflated data, a **percentile fallback** kicks in. `test_outlier_filter.py` exercises this path. Don't bypass the filter without recomputing both branches.
- **Tracking pipeline:** YOLO detection first (Ultralytics), with background-subtraction + template matching as a fallback when YOLO misses; both methods are recorded in the per-frame `detection_method` field. ROIs support Rectangle, Circle, Polygon and can be saved/loaded as templates under `temp/roi_templates`.
- **SAM3 (optional):** `app/routers/tracking.py` adds `temp/models/` to `sys.path` and tries `from sam3.model_builder import build_sam3_video_model`. If the package isn't dropped into `temp/models/sam3/`, `SAM3_AVAILABLE` is False and SAM3-specific endpoints degrade — this is expected, not a bug.
- **Results export:** JSON with ffmpeg-derived timestamps, centroids, active ROI per frame, detection method, and aggregate statistics. The frontend streams large JSONs via `/api/analysis/upload-large-json` (10-minute timeout) — don't try to load multi-hundred-MB results through the synchronous endpoint.
- **Experiment Recording (live):** `app/processing/live_experiment.py` owns a daemon-thread loop that consumes `camera_state["stream"]`, runs YOLO per frame, writes raw video + tracking JSONL + events JSONL + `metadata.json` into `temp/experiments/<exp_id>/`, and emits events to `EventBus`. The router (`app/routers/experiment.py`) exposes lifecycle endpoints and the WebSocket. Hardware bindings (Arduino serial, ESP32 HTTP) live in `app/services/integrations.py` and persist in `temp/integrations.json`. **Singleton:** one experiment per process — `POST /start` is 409 if another is running. **Annotated display:** the loop writes the annotated frame into `camera_state["annotated_frame"]`; `/api/camera/frame` prefers it when present, so the existing frontend polling shows overlays without a new endpoint. **Crash recovery:** see the orphan-marking note in *Running* above.
- **GPU fallback:** at experiment start the backend probes whether PyTorch supports the local GPU arch and falls back to CPU when not (see commit `0e4e33a`). Tracking still runs, just slower — don't treat CPU mode as an error.
