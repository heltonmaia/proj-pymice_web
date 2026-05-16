"""Experiment Recording API.

Owns:
  - LiveExperiment singleton (one per process)
  - REST endpoints for lifecycle, integrations, triggers, ROI updates
  - WebSocket /events channel
  - Action dispatcher that bridges trigger fires -> integration adapters

External callers (the camera router, the shutdown event in main) interact
with the experiment lifecycle via the small helpers `is_experiment_running()`
and `abort_running_experiment()`. This avoids circular imports.
"""

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.models.schemas import (
    ApiResponse,
    ExperimentStartRequest,
    Integration,
    ROIPreset,
    TriggerRule,
)
from app.processing.live_experiment import LiveExperiment
from app.routers.camera import camera_state
from app.services.event_bus import EventBus
from app.services.integrations import (
    HttpAdapter,
    InvalidHostError,
    SerialAdapter,
    create_integration,
    delete_integration,
    list_integrations,
    list_serial_ports,
)


router = APIRouter()
logger = logging.getLogger("pymice.experiment")

_bus = EventBus()
_experiment_state: Dict[str, Optional[LiveExperiment]] = {"current": None}
_adapters: Dict[str, object] = {}
_main_loop_ref: Dict[str, Optional[asyncio.AbstractEventLoop]] = {"loop": None}


def is_experiment_running() -> bool:
    exp = _experiment_state.get("current")
    return exp is not None and exp._state == "running"


def abort_running_experiment(reason: str = "external") -> bool:
    """Stop a running experiment if any. Returns True if it stopped one."""
    exp = _experiment_state.get("current")
    if exp is None or exp._state != "running":
        return False
    try:
        exp.stop(reason)
        logger.info("aborted running experiment (reason=%s)", reason)
        return True
    except Exception as e:
        logger.exception("abort_running_experiment failed: %s", e)
        return False


def _stream_provider():
    return camera_state.get("stream")


def _annotated_frame_setter(frame):
    with camera_state["annotated_lock"]:
        camera_state["annotated_frame"] = frame


def _get_or_open_adapter(integration_id: str) -> Optional[object]:
    if integration_id in _adapters:
        return _adapters[integration_id]
    for integ in list_integrations():
        if integ.id != integration_id:
            continue
        if integ.kind == "serial":
            adapter = SerialAdapter(integ)
        elif integ.kind == "http":
            adapter = HttpAdapter(integ)
        else:
            return None
        _adapters[integration_id] = adapter
        return adapter
    return None


def _dispatch_action(rule: dict, fire: dict) -> dict:
    """Called from the LiveExperiment loop thread.

    Schedules the actual async send onto the main asyncio loop and waits
    for the result (bounded by timeout_sec).
    """
    action = rule.get("action") or {}
    kind = action.get("kind", "integration")
    if kind == "log":
        return {"ok": True, "logged": action.get("label") or rule.get("id")}

    integration_id = action.get("integration_id")
    adapter = _get_or_open_adapter(integration_id) if integration_id else None
    if adapter is None:
        return {"ok": False, "error": f"unknown integration {integration_id}"}

    payload = action.get("payload")
    timeout = float(action.get("timeout_sec") or 2.0)

    loop = _main_loop_ref.get("loop")
    if loop is None:
        return {"ok": False, "error": "main loop not set"}

    fut = asyncio.run_coroutine_threadsafe(adapter.send(payload), loop)
    try:
        return fut.result(timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": f"dispatch_error: {e}"}


@router.on_event("startup")
async def _capture_main_loop():
    _main_loop_ref["loop"] = asyncio.get_event_loop()


# --- experiment lifecycle ---

@router.post("/start")
async def start_experiment(request: ExperimentStartRequest):
    if _experiment_state["current"] is not None and _experiment_state["current"]._state == "running":
        raise HTTPException(status_code=409, detail="Experiment already running")
    if camera_state.get("stream") is None:
        raise HTTPException(status_code=409, detail="No active camera stream - start stream first")

    model_path = os.path.join("temp/models", request.model_name)
    if not os.path.exists(model_path):
        available = [f for f in os.listdir("temp/models") if f.endswith(".pt")] if os.path.exists("temp/models") else []
        raise HTTPException(status_code=400, detail={"error": "model_not_found", "available": available})

    # Validate destination — reject path traversal and force absolute or relative-to-cwd
    safe_base = (request.output_base_dir or "temp/experiments").strip()
    if ".." in safe_base.split(os.sep):
        raise HTTPException(status_code=400, detail="output_base_dir cannot contain '..'")
    try:
        os.makedirs(safe_base, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Cannot create output dir: {e}")

    # Defensive: if a previous experiment is still in 'stopped' but the singleton
    # ref is alive, drop it so we don't leak references to closed file handles.
    prev = _experiment_state.get("current")
    if prev is not None and prev._state != "running":
        logger.info("clearing previous experiment singleton (exp_id=%s, state=%s)",
                    prev.exp_id, prev._state)
        _experiment_state["current"] = None

    exp = LiveExperiment(
        request=request,
        event_bus=_bus,
        stream_provider=_stream_provider,
        annotated_frame_setter=_annotated_frame_setter,
        action_dispatcher=_dispatch_action,
        base_dir=safe_base,
    )
    try:
        exp.start()
    except Exception as e:
        logger.exception("experiment start failed (exp_id=%s): %s", exp.exp_id, e)
        # Cleanup partial state so the next attempt isn't poisoned.
        try:
            if exp._writer_thread is not None:
                exp._writer_thread.stop(0, 0.0, timeout=2.0)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"experiment start failed: {e}")
    _experiment_state["current"] = exp
    logger.info("experiment started (exp_id=%s, output=%s)", exp.exp_id, safe_base)
    return ApiResponse(
        success=True,
        data={"exp_id": exp.exp_id, "ws_url": "/api/experiment/events"},
    )


@router.post("/stop")
async def stop_experiment():
    exp = _experiment_state["current"]
    if exp is None or exp._state != "running":
        raise HTTPException(status_code=404, detail="No running experiment")
    exp.stop("user")
    with camera_state["annotated_lock"]:
        camera_state["annotated_frame"] = None
    return ApiResponse(
        success=True,
        data={
            "exp_id": exp.exp_id,
            "exp_dir": exp._artifacts.exp_dir,
            "segments": exp._recorder.segments() if exp._recorder is not None else [],
        },
    )


@router.get("/artifacts/{exp_id}")
async def artifacts_list(exp_id: str):
    """List every file inside the experiment directory with size+kind metadata."""
    # find the exp_dir under any known output base — checking ./temp/experiments first
    # plus the recorded exp_dir on the singleton if it matches.
    candidate_dirs = ["temp/experiments"]
    exp = _experiment_state["current"]
    if exp is not None and exp.exp_id == exp_id:
        candidate_dirs.insert(0, os.path.dirname(exp._artifacts.exp_dir))
    exp_dir = None
    for base in candidate_dirs:
        path = os.path.join(base, exp_id)
        if os.path.isdir(path):
            exp_dir = path
            break
    if exp_dir is None:
        raise HTTPException(status_code=404, detail="experiment not found")

    files = []
    for name in sorted(os.listdir(exp_dir)):
        full = os.path.join(exp_dir, name)
        if not os.path.isfile(full):
            continue
        kind = (
            "video" if name.startswith("raw_") and name.endswith(".mp4")
            else "tracking" if name.startswith("tracking_") and name.endswith(".jsonl")
            else "events" if name == "events.jsonl"
            else "metadata" if name == "metadata.json"
            else "other"
        )
        files.append(
            {
                "name": name,
                "kind": kind,
                "size": os.path.getsize(full),
            }
        )
    return ApiResponse(
        success=True,
        data={"exp_id": exp_id, "exp_dir": exp_dir, "files": files},
    )


@router.get("/status")
async def status():
    exp = _experiment_state["current"]
    if exp is None:
        return ApiResponse(success=True, data={"state": "idle"})
    return ApiResponse(success=True, data=exp.status())


# --- WebSocket events ---

@router.websocket("/events")
async def events_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        async for event in _bus.subscribe():
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


# --- integrations ---

@router.get("/serial-ports")
async def serial_ports():
    try:
        return ApiResponse(success=True, data={"ports": list_serial_ports()})
    except PermissionError as e:
        return ApiResponse(
            success=False,
            error=f"PermissionError: {e}. Add your user to the 'dialout' group on Linux.",
        )


@router.get("/integrations")
async def integrations_list():
    items = [i.model_dump() for i in list_integrations()]
    return ApiResponse(success=True, data={"integrations": items})


@router.post("/integrations")
async def integrations_create(integration: Integration):
    try:
        created = create_integration(integration)
    except InvalidHostError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(success=True, data=created.model_dump())


@router.delete("/integrations/{integration_id}")
async def integrations_delete(integration_id: str, force: bool = False):
    exp = _experiment_state["current"]
    if exp is not None and exp._state == "running":
        referenced = [
            r.id for r in exp.list_triggers()
            if r.action.integration_id == integration_id
        ]
        if referenced and not force:
            raise HTTPException(
                status_code=409,
                detail={"error": "in_use", "triggers": referenced},
            )
        if force:
            for tid in referenced:
                exp.remove_trigger(tid)
    if integration_id in _adapters:
        adapter = _adapters.pop(integration_id)
        if hasattr(adapter, "close"):
            try:
                if asyncio.iscoroutinefunction(adapter.close):
                    await adapter.close()
                else:
                    adapter.close()
            except Exception:
                pass
    ok = delete_integration(integration_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return ApiResponse(success=True, data={"deleted": integration_id})


@router.post("/integrations/{integration_id}/test")
async def integrations_test(integration_id: str):
    adapter = _get_or_open_adapter(integration_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="integration not found")
    if hasattr(adapter, "send"):
        result = await adapter.send("PING")
        return ApiResponse(success=result.get("ok", False), data=result)
    raise HTTPException(status_code=500, detail="adapter has no send")


# --- triggers ---

@router.get("/triggers")
async def triggers_list():
    exp = _experiment_state["current"]
    if exp is None or exp._state != "running":
        return ApiResponse(success=True, data={"triggers": []})
    return ApiResponse(
        success=True,
        data={"triggers": [r.model_dump() for r in exp.list_triggers()]},
    )


@router.post("/triggers")
async def triggers_create(rule: TriggerRule):
    exp = _experiment_state["current"]
    if exp is None or exp._state != "running":
        raise HTTPException(status_code=404, detail="No running experiment")
    exp.add_trigger(rule)
    return ApiResponse(success=True, data=rule.model_dump())


@router.delete("/triggers/{trigger_id}")
async def triggers_delete(trigger_id: str):
    exp = _experiment_state["current"]
    if exp is None or exp._state != "running":
        raise HTTPException(status_code=404, detail="No running experiment")
    if not exp.remove_trigger(trigger_id):
        raise HTTPException(status_code=404, detail="trigger not found")
    return ApiResponse(success=True, data={"deleted": trigger_id})


# --- ROI live edit ---

@router.post("/rois")
async def rois_update(preset: ROIPreset):
    exp = _experiment_state["current"]
    if exp is None or exp._state != "running":
        raise HTTPException(status_code=404, detail="No running experiment")
    exp.update_rois(preset)
    return ApiResponse(success=True, data={"updated": True})


@router.post("/rois/pause-eval")
async def rois_pause_eval(paused: bool = True):
    exp = _experiment_state["current"]
    if exp is None or exp._state != "running":
        raise HTTPException(status_code=404, detail="No running experiment")
    exp.set_paused_roi_eval(paused)
    return ApiResponse(success=True, data={"paused": paused})


# --- artifact download ---

_ARTIFACT_NAME_RE = re.compile(
    r"^(raw_\d{3}\.mp4|tracking_\d{3}\.jsonl|events\.jsonl|metadata\.json)$"
)


@router.get("/artifacts/{exp_id}/{artifact}")
async def artifact_download(exp_id: str, artifact: str):
    if not _ARTIFACT_NAME_RE.match(artifact):
        raise HTTPException(status_code=400, detail="invalid artifact name")
    candidate_dirs = ["temp/experiments"]
    exp = _experiment_state["current"]
    if exp is not None and exp.exp_id == exp_id:
        candidate_dirs.insert(0, os.path.dirname(exp._artifacts.exp_dir))
    for base in candidate_dirs:
        path = os.path.join(base, exp_id, artifact)
        if os.path.exists(path):
            return FileResponse(path, filename=f"{exp_id}_{artifact}")
    raise HTTPException(status_code=404, detail="not found")
