"""Experiment Recording API.

Owns:
  - LiveExperiment singleton (one per process)
  - REST endpoints for lifecycle, integrations, triggers, ROI updates
  - WebSocket /events channel
  - Action dispatcher that bridges trigger fires -> integration adapters
"""

import asyncio
import os
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

_bus = EventBus()
_experiment_state: Dict[str, Optional[LiveExperiment]] = {"current": None}
_adapters: Dict[str, object] = {}
_main_loop_ref: Dict[str, Optional[asyncio.AbstractEventLoop]] = {"loop": None}


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

    exp = LiveExperiment(
        request=request,
        event_bus=_bus,
        stream_provider=_stream_provider,
        annotated_frame_setter=_annotated_frame_setter,
        action_dispatcher=_dispatch_action,
    )
    try:
        exp.start()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    _experiment_state["current"] = exp
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
    artifacts = {
        "raw_video": exp._artifacts.raw_video,
        "tracking_jsonl": exp._artifacts.tracking_jsonl,
        "events_jsonl": exp._artifacts.events_jsonl,
        "metadata_json": exp._artifacts.metadata_json,
    }
    with camera_state["annotated_lock"]:
        camera_state["annotated_frame"] = None
    return ApiResponse(success=True, data={"exp_id": exp.exp_id, "artifacts": artifacts})


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

@router.get("/artifacts/{exp_id}/{artifact}")
async def artifact_download(exp_id: str, artifact: str):
    allowed = {"raw.mp4", "tracking.jsonl", "events.jsonl", "metadata.json"}
    if artifact not in allowed:
        raise HTTPException(status_code=400, detail="invalid artifact")
    path = os.path.join("temp/experiments", exp_id, artifact)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, filename=f"{exp_id}_{artifact}")
