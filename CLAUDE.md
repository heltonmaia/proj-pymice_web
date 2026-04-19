# CLAUDE.md — proj-pymice_web

Project context and conventions for Claude Code. Instructions here take precedence over generic defaults.

## Project Overview
- **Name:** proj-pymice_web (PyMice Web)
- **Purpose:** Web application for mouse tracking and behavioral/ethological analysis (Open Field, heatmaps, trajectories, ROI-based metrics).
- **Architecture:** Monorepo under `pymice/` with a FastAPI backend and a React + TypeScript frontend.

## Stack
- **Frontend:** React 18 + TypeScript, Vite, TailwindCSS, Axios, Lucide React.
- **Backend:** Python 3.11, FastAPI, Pydantic, PyTorch 2.6.0 (CUDA 12.4), Ultralytics 8.3.102 (YOLO), OpenCV, ffmpeg/ffprobe.
- **Python packaging:** `uv` (always — do not use pip/poetry/conda for this repo).

## Layout
```
proj-pymice_web/
├── pymice/
│   ├── backend/          # FastAPI app (app/routers, app/models, app/processing, app/main.py)
│   ├── frontend/         # React app (src/components, src/pages, src/services, src/types, src/utils)
│   ├── logs/             # Runtime logs
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
- Preferred: `./pymice/run.sh start` (also: `status`, `stop`, `restart`, or run with no args for interactive menu). `run.sh` uses relative paths, so launch it from `pymice/`.
- Frontend dev: http://localhost:5765 — Backend: http://localhost:8765 — Docs: http://localhost:8765/docs.
- Logs: `tail -f pymice/logs/*.log`.

## Conventions
- Keep environment setup reproducible — any new dependency goes through `uv` and is reflected in `pyproject.toml` / `uv.lock`.
- Frontend styling: Tailwind utility classes; avoid ad-hoc CSS unless necessary.
- Backend: follow FastAPI conventions (routers in `app/routers`, Pydantic schemas in `app/models`, processing/CV/ML logic in `app/processing`).
- Be mindful of CWD when running scripts — `run.sh` lives in `pymice/`, not the repo root.

## Domain notes
- Heatmap uses **Power Normalization** with gamma=0.4 to expand low-density regions; colorbar is normalized 0–1.
- Tracking combines YOLO detection with template-matching fallback; ROIs support Rectangle, Circle, Polygon and can be saved/loaded as templates.
- Results export is JSON with ffmpeg-derived timestamps, centroids, active ROI per frame, detection method, and aggregate statistics.
