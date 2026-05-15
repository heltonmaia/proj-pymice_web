# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
- **Name:** proj-pymice_web (PyMice Web)
- **Purpose:** Web application for mouse tracking and behavioral/ethological analysis (Open Field, heatmaps, trajectories, ROI-based metrics).
- **Architecture:** Monorepo under `pymice/` with a FastAPI backend and a React + TypeScript frontend.

## Stack
- **Frontend:** React 18 + TypeScript, Vite, TailwindCSS, Axios, Lucide React, Zustand (state), React Query, React-Konva (interactive ROI drawing), Recharts.
- **Backend:** Python 3.11, FastAPI, Pydantic, PyTorch 2.6.0 (CUDA 12.4), Ultralytics 8.3.102 (YOLO), OpenCV, ffmpeg/ffprobe. Optional SAM3 support (see Domain notes).
- **Python packaging:** `uv` (always — do not use pip/poetry/conda for this repo). `pymice/backend/requirements.txt` is kept only as a fallback/reference; `pyproject.toml` + `uv.lock` are the source of truth.

## Layout
```
proj-pymice_web/
├── pymice/
│   ├── backend/          # FastAPI app
│   │   └── app/
│   │       ├── main.py        # Entry point + startup cleanup
│   │       ├── routers/       # camera, video, tracking, roi, analysis, system
│   │       ├── models/        # Pydantic schemas
│   │       └── processing/    # detection.py, tracking.py (YOLO + template matching)
│   ├── frontend/         # React app
│   │   └── src/
│   │       ├── App.tsx        # Tab shell (locks tabs during tracking)
│   │       ├── pages/         # One file per tab (CameraTab, TrackingTab, …)
│   │       ├── services/api.ts # Axios client, all backend endpoints
│   │       └── components, hooks, store, types, utils
│   ├── logs/             # Runtime logs (backend.log, frontend.log, *.pid)
│   ├── run.sh            # Unified start/stop/status script
│   └── setup_backend.sh  # Backend environment setup
├── uv-env  → /mnt/hd3/uv-common/pymice-react-venv   (symlink to UV virtualenv)
├── .venv   → same target as uv-env
└── README.md
```

## Environment
- **UV venv:** `uv-env/` (symlink → `/mnt/hd3/uv-common/pymice-react-venv`; venv dir kept under its historical name). Activate with `source uv-env/bin/activate` from repo root, or `source ../uv-env/bin/activate` from `pymice/backend/`.
- **UV cache:** `/mnt/hd3/uv-common/uv-web`.
- **GPU check:** `python -c "import torch; print(torch.cuda.is_available())"`.

## Running
- Preferred: `./pymice/run.sh start` (also: `status`, `stop`, `restart`, `clean`, `logs [backend|frontend]`, or run with no args for interactive menu). `run.sh` uses relative paths, so launch it from `pymice/`. A `run.bat` exists for Windows; keep it in sync if you change `run.sh` semantics.
- **`run.sh` does not activate the venv** — it requires `$VIRTUAL_ENV` to already be set and will exit with an error otherwise. Activate `uv-env/bin/activate` first.
- `run.sh start` also calls `clean_temporaries` and the backend `startup_event` clears `temp/{videos,tracking,analysis,roi_templates}` (files >1h old) — anything you stage there for debugging may be wiped on next start. `temp/models/*.pt` is explicitly preserved.
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
- **Backend formatting/lint:** dev extras provide `black` (line-length 100), `isort` (black profile), `flake8`, `pytest`. Install with `uv pip install -e '.[dev]'`. There is no project-wide test suite yet; the standalone scripts in `pymice/backend/` (`test_cuda.py`, `test_sam3.py`, `test_outlier_filter.py`) are probes — run them directly with `python <file>` rather than via `pytest`.

## API surface
Routers are mounted in `app/main.py`:
- `/api/camera` — device list, live stream, recording.
- `/api/video` — upload, info, frame, download, list.
- `/api/tracking` — YOLO models, start/stop/progress, results, ROI templates, test-detection, batch prepare.
- `/api/roi` — named ROI presets.
- `/api/analysis` — heatmap, movement, complete analysis, Open Field, video export, large-JSON upload/load.
- `/api/system` — GPU check, YOLO benchmark.

CORS is hard-coded to `http://localhost:3000` and `http://localhost:5765` — update `app/main.py` if you change the frontend port.

## Conventions
- Keep environment setup reproducible — any new Python dependency goes through `uv` and is reflected in `pyproject.toml` / `uv.lock`.
- Frontend styling: Tailwind utility classes; dark mode is class-based (`dark:` variants throughout) and toggled via `components/ThemeToggle.tsx` + `hooks/useTheme.ts`. Avoid ad-hoc CSS unless necessary.
- Frontend path alias: `@/` → `src/` (set in `vite.config.ts` and `tsconfig.json`). Use it for cross-tree imports.
- Backend: follow FastAPI conventions (routers in `app/routers`, Pydantic schemas in `app/models`, processing/CV/ML logic in `app/processing`). `app/services` and `app/utils` exist but are currently empty — put cross-router helpers there rather than inline in routers.
- Be mindful of CWD when running scripts — `run.sh` lives in `pymice/`, not the repo root, and the backend resolves `temp/` relative to `pymice/backend/`.

## Domain notes
- **Heatmap:** **Power Normalization** with gamma=0.4 to expand low-density regions; colorbar is normalized 0–1. Don't switch to linear without a reason — it makes low-traffic areas invisible next to hotspots.
- **Ethological analysis (`EthologicalTab.tsx` + `app/routers/analysis.py`):** primary surface for post-tracking metrics — Velocity and Activity cards live side-by-side here. Velocity uses a **Median + k·MAD** outlier filter; when MAD collapses to zero on quantized/zero-inflated data, a **percentile fallback** kicks in. `test_outlier_filter.py` exercises this path. Don't bypass the filter without recomputing both branches.
- **Tracking pipeline:** YOLO detection first (Ultralytics), with background-subtraction + template matching as a fallback when YOLO misses; both methods are recorded in the per-frame `detection_method` field. ROIs support Rectangle, Circle, Polygon and can be saved/loaded as templates under `temp/roi_templates`.
- **SAM3 (optional):** `app/routers/tracking.py` adds `temp/models/` to `sys.path` and tries `from sam3.model_builder import build_sam3_video_model`. If the package isn't dropped into `temp/models/sam3/`, `SAM3_AVAILABLE` is False and SAM3-specific endpoints degrade — this is expected, not a bug.
- **Results export:** JSON with ffmpeg-derived timestamps, centroids, active ROI per frame, detection method, and aggregate statistics. The frontend streams large JSONs via `/api/analysis/upload-large-json` (10-minute timeout) — don't try to load multi-hundred-MB results through the synchronous endpoint.
