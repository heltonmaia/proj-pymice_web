# Experiment Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Camera tab with an "Experiment Recording" tab that runs YOLO live tracking on a USB camera, lets the user draw and edit ROIs in real time, records raw video plus a per-frame tracking JSONL, and fires triggers to Arduino/ESP32 (or HTTP endpoints) when ROI events match user rules.

**Architecture:** Backend-owned capture/detect loop reading from `camera_state["stream"]`, emitting events to an in-process EventBus consumed by a WebSocket subscriber. Frontend keeps the existing 30 Hz frame-polling for display and reuses a new shared `<ROICanvas>` component (extracted from TrackingTab) for both ROI drawing and live overlay.

**Tech Stack:** FastAPI, OpenCV, Ultralytics YOLO, pyserial, httpx, React + TypeScript, react-konva (already used for ROI drawing).

**Reference spec:** `docs/superpowers/specs/2026-05-15-experiment-recording-design.md` (approved).

---

## File Structure

### Backend — new files
- `pymice/backend/app/services/event_bus.py` — in-process pub/sub
- `pymice/backend/app/services/integrations.py` — registry + SerialAdapter + HttpAdapter
- `pymice/backend/app/processing/live_experiment.py` — `LiveExperiment` class + loop
- `pymice/backend/app/processing/trigger_evaluator.py` — rule matching + per-trigger state
- `pymice/backend/app/routers/experiment.py` — REST + WS
- `pymice/backend/tests/__init__.py`
- `pymice/backend/tests/conftest.py`
- `pymice/backend/tests/test_event_bus.py`
- `pymice/backend/tests/test_trigger_evaluator.py`
- `pymice/backend/tests/test_integration_serial.py`
- `pymice/backend/tests/test_integration_http.py`
- `pymice/backend/tests/test_live_experiment_loop.py`

### Backend — modified files
- `pymice/backend/app/models/schemas.py` — add experiment/integration/trigger schemas
- `pymice/backend/app/routers/camera.py` — `/frame` prefers `camera_state["annotated_frame"]`
- `pymice/backend/app/main.py` — register experiment router; exclude `temp/experiments/` and `temp/integrations.json` from cleanup; mark orphans on startup
- `pymice/backend/pyproject.toml` — add `pyserial`, `httpx` (if not already there)

### Frontend — new files
- `pymice/frontend/src/components/ROICanvas.tsx` — shared drawing/overlay component
- `pymice/frontend/src/pages/ExperimentRecordingTab.tsx` — replaces CameraTab (renamed, expanded)
- `pymice/frontend/src/components/IntegrationsPanel.tsx`
- `pymice/frontend/src/components/TriggersPanel.tsx`
- `pymice/frontend/src/components/EventLogPanel.tsx`

### Frontend — modified files
- `pymice/frontend/src/pages/TrackingTab.tsx` — consume `<ROICanvas>` instead of inline drawing
- `pymice/frontend/src/pages/CameraTab.tsx` — DELETED (replaced)
- `pymice/frontend/src/App.tsx` — swap CameraTab import for ExperimentRecordingTab; cover experiment-active in tab-lock logic
- `pymice/frontend/src/services/api.ts` — add `experimentApi`
- `pymice/frontend/src/types/index.ts` — add types for Integration, TriggerRule, ExperimentEvent

### Docs — modified files
- `pymice/CLAUDE.md` (or root `CLAUDE.md`) — add `/api/experiment` to API surface; add live pipeline + integrations to Domain notes
- `docs/diferenciais.md` — update with live experiment + hardware integration capability

---

## Task 1: Add dependencies and core schemas

**Files:**
- Modify: `pymice/backend/pyproject.toml`
- Modify: `pymice/backend/app/models/schemas.py`

- [ ] **Step 1: Add pyserial and httpx to pyproject.toml**

Open `pymice/backend/pyproject.toml`, find the `[project] dependencies` array, and add:

```toml
"pyserial>=3.5",
"httpx>=0.27",
```

(If `httpx` is already there via FastAPI, leave the existing pin.)

- [ ] **Step 2: Install dependencies**

```bash
source uv-env/bin/activate
cd pymice/backend
uv pip install -e .
```

Expected: pyserial installs cleanly. `python -c "import serial; import httpx; print('ok')"` → `ok`.

- [ ] **Step 3: Add experiment schemas to schemas.py**

Append at the end of `pymice/backend/app/models/schemas.py`:

```python
# --- Experiment Recording (live) ---

class TriggerMatch(BaseModel):
    event_type: Literal["roi_entry", "roi_exit", "tick", "frame_drop"]
    roi_name: Optional[str] = None
    min_dwell_sec: Optional[float] = None
    cooldown_sec: Optional[float] = 0.0


class TriggerAction(BaseModel):
    integration_id: Optional[str] = None  # required unless kind == "log"
    kind: Literal["integration", "log"] = "integration"
    payload: Optional[Union[str, dict]] = None
    label: Optional[str] = None  # for kind="log"
    timeout_sec: float = 2.0


class TriggerRule(BaseModel):
    id: str
    name: str
    match: TriggerMatch
    action: TriggerAction


class IntegrationConfigSerial(BaseModel):
    port: str
    baud: int = 115200
    newline: str = "\n"


class IntegrationConfigHttp(BaseModel):
    base_url: str
    default_method: Literal["GET", "POST", "PUT"] = "POST"
    default_timeout_sec: float = 2.0
    headers: dict = Field(default_factory=dict)


class Integration(BaseModel):
    id: str
    name: str
    kind: Literal["serial", "http"]
    config: Union[IntegrationConfigSerial, IntegrationConfigHttp]


class ExperimentStartRequest(BaseModel):
    device_id: int
    model_name: str
    rois: ROIPreset
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    inference_size: int = Field(default=640, ge=320, le=1280)
    fps_target: Optional[float] = None  # None = use camera-native FPS
    max_consecutive_drops: int = 30
    triggers: List[TriggerRule] = Field(default_factory=list)


class ExperimentStatus(BaseModel):
    exp_id: Optional[str] = None
    state: Literal["idle", "running", "stopped", "crashed"]
    started_at: Optional[str] = None
    frames_processed: int = 0
    fps_actual: float = 0.0
    detections: int = 0
    events_emitted: int = 0
    last_active_roi: Optional[int] = None


class ExperimentEvent(BaseModel):
    type: str
    frame_idx: Optional[int] = None
    t: Optional[float] = None
    # additional fields by type, see spec
```

- [ ] **Step 4: Verify import works**

```bash
cd pymice/backend
python -c "from app.models.schemas import ExperimentStartRequest, Integration, TriggerRule; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add pymice/backend/pyproject.toml pymice/backend/uv.lock pymice/backend/app/models/schemas.py
git commit -m "feat(experiment): add schemas and pyserial/httpx deps"
```

---

## Task 2: Create pytest scaffolding

**Files:**
- Create: `pymice/backend/tests/__init__.py`
- Create: `pymice/backend/tests/conftest.py`

- [ ] **Step 1: Create test directory and __init__.py**

```bash
mkdir -p pymice/backend/tests
touch pymice/backend/tests/__init__.py
```

- [ ] **Step 2: Create conftest.py**

Create `pymice/backend/tests/conftest.py`:

```python
"""Shared pytest fixtures for backend tests."""

import asyncio
import pytest


@pytest.fixture
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()
```

- [ ] **Step 3: Verify pytest discovers the directory**

```bash
cd pymice/backend
pytest tests/ --collect-only
```

Expected: 0 tests collected, no errors.

- [ ] **Step 4: Commit**

```bash
git add pymice/backend/tests/__init__.py pymice/backend/tests/conftest.py
git commit -m "test: scaffold pytest tests/ directory"
```

---

## Task 3: EventBus pub/sub

**Files:**
- Create: `pymice/backend/tests/test_event_bus.py`
- Create: `pymice/backend/app/services/event_bus.py`

- [ ] **Step 1: Write failing test**

Create `pymice/backend/tests/test_event_bus.py`:

```python
"""Tests for the in-process event bus."""

import asyncio
import pytest

from app.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_reaches_subscriber():
    bus = EventBus()
    received = []

    async def consumer():
        async for evt in bus.subscribe():
            received.append(evt)
            if len(received) == 2:
                return

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let consumer subscribe
    bus.publish({"type": "a"})
    bus.publish({"type": "b"})
    await asyncio.wait_for(task, timeout=1.0)

    assert received == [{"type": "a"}, {"type": "b"}]


@pytest.mark.asyncio
async def test_slow_subscriber_overflows_and_is_dropped():
    bus = EventBus(maxsize=2)

    async def slow_consumer():
        # Subscribe but never read
        sub = bus._make_subscription()
        try:
            await asyncio.sleep(10)
        finally:
            sub.close()
        return sub

    # Manually create subscription and don't drain it
    sub = bus._make_subscription()
    bus.publish({"type": "a"})
    bus.publish({"type": "b"})
    bus.publish({"type": "c"})  # should overflow → drop

    assert sub.dropped is True


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_all():
    bus = EventBus()
    a_received = []
    b_received = []

    async def consumer(target):
        async for evt in bus.subscribe():
            target.append(evt)
            if len(target) == 1:
                return

    task_a = asyncio.create_task(consumer(a_received))
    task_b = asyncio.create_task(consumer(b_received))
    await asyncio.sleep(0)
    bus.publish({"type": "x"})
    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=1.0)

    assert a_received == [{"type": "x"}]
    assert b_received == [{"type": "x"}]
```

Add `pytest-asyncio` to dev deps if missing:

```bash
uv pip install pytest-asyncio
```

And in `pymice/backend/pyproject.toml`, under `[tool.pytest.ini_options]` (create section if absent):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
cd pymice/backend
pytest tests/test_event_bus.py -v
```

Expected: ImportError on `from app.services.event_bus import EventBus`.

- [ ] **Step 3: Implement EventBus**

Create `pymice/backend/app/services/event_bus.py`:

```python
"""In-process pub/sub event bus.

Publishers call publish() synchronously (from the LiveExperiment loop thread).
Subscribers iterate via subscribe() in asyncio context. A subscriber whose
queue overflows is marked dropped — the WebSocket handler closes its socket
in that case. The canonical record is always events.jsonl on disk; the bus
is best-effort delivery.
"""

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, List


@dataclass
class _Subscription:
    queue: asyncio.Queue
    dropped: bool = False
    closed: bool = False

    def close(self):
        self.closed = True


class EventBus:
    def __init__(self, maxsize: int = 1024):
        self._maxsize = maxsize
        self._subs: List[_Subscription] = []
        self._lock = asyncio.Lock()

    def _make_subscription(self) -> _Subscription:
        sub = _Subscription(queue=asyncio.Queue(maxsize=self._maxsize))
        self._subs.append(sub)
        return sub

    def publish(self, event: dict) -> None:
        # Iterate over a snapshot to allow concurrent unsubscribe.
        for sub in list(self._subs):
            if sub.closed:
                self._subs.remove(sub)
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.dropped = True
                sub.close()

    async def subscribe(self) -> AsyncIterator[dict]:
        sub = self._make_subscription()
        try:
            while not sub.closed:
                evt = await sub.queue.get()
                yield evt
                if sub.dropped:
                    return
        finally:
            sub.close()
```

- [ ] **Step 4: Run test, confirm pass**

```bash
pytest tests/test_event_bus.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pymice/backend/tests/test_event_bus.py pymice/backend/app/services/event_bus.py pymice/backend/pyproject.toml
git commit -m "feat(experiment): in-process EventBus with backpressure drop"
```

---

## Task 4: Trigger evaluator

**Files:**
- Create: `pymice/backend/tests/test_trigger_evaluator.py`
- Create: `pymice/backend/app/processing/trigger_evaluator.py`

- [ ] **Step 1: Write failing test**

Create `pymice/backend/tests/test_trigger_evaluator.py`:

```python
"""Tests for the per-frame trigger evaluator."""

from app.processing.trigger_evaluator import TriggerEvaluator
from app.models.schemas import TriggerRule, TriggerMatch, TriggerAction


def _rule(rule_id, event_type, roi_name=None, min_dwell=None, cooldown=0.0):
    return TriggerRule(
        id=rule_id,
        name=rule_id,
        match=TriggerMatch(
            event_type=event_type,
            roi_name=roi_name,
            min_dwell_sec=min_dwell,
            cooldown_sec=cooldown,
        ),
        action=TriggerAction(kind="log", label=rule_id),
    )


def test_simple_match():
    ev = TriggerEvaluator([_rule("t1", "roi_entry", roi_name="center")])
    fires = ev.evaluate(
        [{"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.1}]
    )
    assert [f["trigger_id"] for f in fires if not f.get("skipped")] == ["t1"]


def test_filter_by_roi_name():
    ev = TriggerEvaluator([_rule("t1", "roi_entry", roi_name="center")])
    fires = ev.evaluate(
        [{"type": "roi_entry", "roi_name": "edge", "frame_idx": 1, "t": 0.1}]
    )
    assert fires == []


def test_cooldown_silences_second_fire():
    ev = TriggerEvaluator([_rule("t1", "roi_entry", roi_name="center", cooldown=5.0)])
    e1 = {"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.0}
    e2 = {"type": "roi_entry", "roi_name": "center", "frame_idx": 60, "t": 2.0}
    e3 = {"type": "roi_entry", "roi_name": "center", "frame_idx": 200, "t": 10.0}
    f1 = ev.evaluate([e1])
    f2 = ev.evaluate([e2])
    f3 = ev.evaluate([e3])

    # First fires, second is skipped:cooldown, third fires
    assert [f for f in f1 if not f.get("skipped")] != []
    assert [f for f in f2 if f.get("skipped") == "cooldown"] != []
    assert [f for f in f3 if not f.get("skipped")] != []


def test_min_dwell_filters_short_visits():
    ev = TriggerEvaluator([_rule("t1", "roi_exit", roi_name="center", min_dwell=1.0)])
    entry = {"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.0}
    short_exit = {"type": "roi_exit", "roi_name": "center", "frame_idx": 10, "t": 0.5}
    long_entry = {"type": "roi_entry", "roi_name": "center", "frame_idx": 50, "t": 5.0}
    long_exit = {"type": "roi_exit", "roi_name": "center", "frame_idx": 200, "t": 10.0}

    # Evaluator must see entries too in order to track dwell start
    ev.evaluate([entry])
    fires_short = ev.evaluate([short_exit])
    ev.evaluate([long_entry])
    fires_long = ev.evaluate([long_exit])

    assert fires_short == []  # below min_dwell
    assert any(not f.get("skipped") for f in fires_long)


def test_multiple_triggers_same_frame():
    ev = TriggerEvaluator(
        [
            _rule("t1", "roi_entry", roi_name="center"),
            _rule("t2", "roi_entry"),  # any roi
        ]
    )
    fires = ev.evaluate(
        [{"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.1}]
    )
    assert {f["trigger_id"] for f in fires if not f.get("skipped")} == {"t1", "t2"}
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/test_trigger_evaluator.py -v
```

Expected: ImportError on `from app.processing.trigger_evaluator import TriggerEvaluator`.

- [ ] **Step 3: Implement TriggerEvaluator**

Create `pymice/backend/app/processing/trigger_evaluator.py`:

```python
"""Per-frame trigger rule evaluator.

Holds per-trigger state (last_fired_at, last_entry_t_per_roi).
evaluate() is called by LiveExperiment after emitting frame events; it
returns a list of fire records (one per match), some marked skipped.
The caller is responsible for executing actions and persisting these
records to events.jsonl / WebSocket.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.schemas import TriggerRule


@dataclass
class _State:
    last_fired_at: Optional[float] = None
    last_entry_t_per_roi: Dict[str, float] = field(default_factory=dict)


class TriggerEvaluator:
    def __init__(self, rules: List[TriggerRule]):
        self._rules = list(rules)
        self._state: Dict[str, _State] = {r.id: _State() for r in self._rules}

    def replace_rules(self, rules: List[TriggerRule]) -> None:
        self._rules = list(rules)
        # Preserve state for rules that still exist
        new_state = {}
        for r in self._rules:
            new_state[r.id] = self._state.get(r.id, _State())
        self._state = new_state

    def evaluate(self, events: List[dict]) -> List[dict]:
        fires: List[dict] = []

        # First, track all roi_entry events to update dwell start times
        for evt in events:
            if evt.get("type") == "roi_entry":
                roi_name = evt.get("roi_name") or ""
                t = evt.get("t", 0.0)
                for rule in self._rules:
                    st = self._state[rule.id]
                    st.last_entry_t_per_roi[roi_name] = t

        for evt in events:
            etype = evt.get("type")
            for rule in self._rules:
                m = rule.match
                if m.event_type != etype:
                    continue
                if m.roi_name is not None and evt.get("roi_name") != m.roi_name:
                    continue

                st = self._state[rule.id]
                t = evt.get("t", 0.0)

                # min_dwell_sec applies to exits
                if etype == "roi_exit" and m.min_dwell_sec is not None:
                    roi_name = evt.get("roi_name") or ""
                    entry_t = st.last_entry_t_per_roi.get(roi_name)
                    if entry_t is None or (t - entry_t) < m.min_dwell_sec:
                        continue  # silent skip (dwell unmet)

                # cooldown
                if m.cooldown_sec and st.last_fired_at is not None:
                    if (t - st.last_fired_at) < m.cooldown_sec:
                        fires.append(
                            {
                                "trigger_id": rule.id,
                                "frame_idx": evt.get("frame_idx"),
                                "t": t,
                                "skipped": "cooldown",
                            }
                        )
                        continue

                st.last_fired_at = t
                fires.append(
                    {
                        "trigger_id": rule.id,
                        "rule": rule.model_dump(),
                        "frame_idx": evt.get("frame_idx"),
                        "t": t,
                    }
                )

        return fires
```

- [ ] **Step 4: Run test, confirm pass**

```bash
pytest tests/test_trigger_evaluator.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pymice/backend/tests/test_trigger_evaluator.py pymice/backend/app/processing/trigger_evaluator.py
git commit -m "feat(experiment): trigger evaluator with cooldown and dwell"
```

---

## Task 5: Integration adapters and registry

**Files:**
- Create: `pymice/backend/tests/test_integration_serial.py`
- Create: `pymice/backend/tests/test_integration_http.py`
- Create: `pymice/backend/app/services/integrations.py`

- [ ] **Step 1: Write failing serial test**

Create `pymice/backend/tests/test_integration_serial.py`:

```python
"""Tests for SerialAdapter."""

import pytest
from unittest.mock import MagicMock, patch

from app.services.integrations import SerialAdapter
from app.models.schemas import Integration, IntegrationConfigSerial


def _serial_integration():
    return Integration(
        id="i-1",
        name="Test",
        kind="serial",
        config=IntegrationConfigSerial(port="/dev/ttyUSB0", baud=115200, newline="\n"),
    )


@pytest.mark.asyncio
async def test_write_sends_payload_with_newline():
    integ = _serial_integration()
    mock_serial = MagicMock()
    with patch("app.services.integrations.serial.Serial", return_value=mock_serial):
        adapter = SerialAdapter(integ)
        result = await adapter.send("DROP")
    assert result["ok"] is True
    mock_serial.write.assert_called_once_with(b"DROP\n")


@pytest.mark.asyncio
async def test_disconnect_during_write_reports_error_and_reopens():
    import serial as pyserial

    integ = _serial_integration()
    fail_then_succeed = MagicMock()
    fail_then_succeed.write.side_effect = [pyserial.SerialException("disconnect"), None]

    with patch("app.services.integrations.serial.Serial", return_value=fail_then_succeed):
        adapter = SerialAdapter(integ)
        first = await adapter.send("A")
        second = await adapter.send("B")

    assert first["ok"] is False
    assert "disconnect" in first["error"].lower() or "serial" in first["error"].lower()
    assert second["ok"] is True
```

- [ ] **Step 2: Write failing http test**

Create `pymice/backend/tests/test_integration_http.py`:

```python
"""Tests for HttpAdapter and whitelist."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.integrations import (
    HttpAdapter,
    create_integration,
    InvalidHostError,
)
from app.models.schemas import Integration, IntegrationConfigHttp


@pytest.mark.asyncio
async def test_localhost_allowed():
    integ = Integration(
        id="i-1",
        name="t",
        kind="http",
        config=IntegrationConfigHttp(base_url="http://localhost:9000"),
    )
    adapter = HttpAdapter(integ)
    # Use MockTransport-like patch on the client
    with patch.object(adapter, "_client") as mock_client:
        mock_client.request = AsyncMock(
            return_value=AsyncMock(status_code=200, text="ok")
        )
        mock_client.request.return_value.status_code = 200
        mock_client.request.return_value.text = "ok"
        result = await adapter.send({"foo": "bar"})
    assert result["ok"] is True
    assert result["status_code"] == 200


def test_lan_192_168_allowed():
    create_integration(  # should not raise
        Integration(
            id="i-2",
            name="lan",
            kind="http",
            config=IntegrationConfigHttp(base_url="http://192.168.1.42"),
        ),
        registry_path=None,  # dry-run, no persistence
    )


def test_public_host_rejected():
    with pytest.raises(InvalidHostError):
        create_integration(
            Integration(
                id="i-3",
                name="bad",
                kind="http",
                config=IntegrationConfigHttp(base_url="http://example.com"),
            ),
            registry_path=None,
        )
```

- [ ] **Step 3: Run tests, confirm they fail**

```bash
pytest tests/test_integration_serial.py tests/test_integration_http.py -v
```

Expected: ImportError on `from app.services.integrations import ...`.

- [ ] **Step 4: Implement integrations module**

Create `pymice/backend/app/services/integrations.py`:

```python
"""Hardware/HTTP integration adapters and registry.

- SerialAdapter holds a pyserial.Serial open for the integration's lifetime,
  reopening on transient errors.
- HttpAdapter holds an httpx.AsyncClient with keep-alive.
- Registry is a JSON file (default: temp/integrations.json) — survives restarts
  and is excluded from cleanup_temp_directories.
"""

import asyncio
import ipaddress
import json
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx
import serial as pyserial
import serial.tools.list_ports

from app.models.schemas import Integration


class InvalidHostError(ValueError):
    pass


# --- whitelist ---

def _is_private_host(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


def _validate_http_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if not parsed.hostname:
        raise InvalidHostError(f"missing hostname: {base_url}")
    if not _is_private_host(parsed.hostname):
        raise InvalidHostError(
            f"host {parsed.hostname!r} not allowed; only localhost/127.0.0.1 and RFC1918 LAN"
        )


# --- adapters ---

class SerialAdapter:
    def __init__(self, integration: Integration):
        self.integration = integration
        cfg = integration.config
        self._port_name = cfg.port
        self._baud = cfg.baud
        self._newline = cfg.newline
        self._sem = asyncio.Semaphore(8)
        self._port: Optional[pyserial.Serial] = None
        self._open()

    def _open(self) -> None:
        try:
            self._port = pyserial.Serial(self._port_name, self._baud, timeout=1)
        except Exception:
            self._port = None

    async def send(self, payload) -> dict:
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        data = (str(payload) + self._newline).encode("utf-8")
        async with self._sem:
            loop = asyncio.get_event_loop()
            try:
                if self._port is None:
                    self._open()
                if self._port is None:
                    return {"ok": False, "error": "port not open"}
                await loop.run_in_executor(None, self._port.write, data)
                return {"ok": True}
            except pyserial.SerialException as e:
                self._port = None  # force reopen next call
                return {"ok": False, "error": f"SerialException: {e}"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
            self._port = None


class HttpAdapter:
    def __init__(self, integration: Integration):
        self.integration = integration
        cfg = integration.config
        _validate_http_base_url(cfg.base_url)
        self._method = cfg.default_method
        self._timeout = cfg.default_timeout_sec
        self._client = httpx.AsyncClient(
            base_url=cfg.base_url,
            headers=cfg.headers,
            timeout=cfg.default_timeout_sec,
        )
        self._sem = asyncio.Semaphore(8)

    async def send(self, payload, path: str = "/", method: Optional[str] = None,
                   timeout_sec: Optional[float] = None) -> dict:
        async with self._sem:
            loop_start = asyncio.get_event_loop().time()
            try:
                kwargs = {}
                if isinstance(payload, dict):
                    kwargs["json"] = payload
                elif payload is not None:
                    kwargs["content"] = str(payload)
                resp = await self._client.request(
                    method or self._method,
                    path,
                    timeout=timeout_sec or self._timeout,
                    **kwargs,
                )
                latency_ms = (asyncio.get_event_loop().time() - loop_start) * 1000
                body = resp.text[:512] if hasattr(resp, "text") else ""
                return {
                    "ok": 200 <= resp.status_code < 400,
                    "status_code": resp.status_code,
                    "latency_ms": round(latency_ms, 1),
                    "body_truncated": body,
                }
            except httpx.TimeoutException:
                return {"ok": False, "error": "timeout"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    async def close(self) -> None:
        await self._client.aclose()


# --- registry ---

DEFAULT_REGISTRY_PATH = "temp/integrations.json"


def _load(path: str) -> List[Integration]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    return [Integration(**item) for item in data]


def _save(path: str, integrations: List[Integration]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([i.model_dump() for i in integrations], f, indent=2)


def list_integrations(registry_path: str = DEFAULT_REGISTRY_PATH) -> List[Integration]:
    return _load(registry_path)


def create_integration(integration: Integration,
                       registry_path: Optional[str] = DEFAULT_REGISTRY_PATH) -> Integration:
    if integration.kind == "http":
        _validate_http_base_url(integration.config.base_url)
    if registry_path is None:
        return integration  # dry-run validation only
    existing = _load(registry_path)
    if any(i.id == integration.id for i in existing):
        raise ValueError(f"integration {integration.id} already exists")
    existing.append(integration)
    _save(registry_path, existing)
    return integration


def delete_integration(integration_id: str,
                       registry_path: str = DEFAULT_REGISTRY_PATH) -> bool:
    existing = _load(registry_path)
    new = [i for i in existing if i.id != integration_id]
    if len(new) == len(existing):
        return False
    _save(registry_path, new)
    return True


def list_serial_ports() -> List[dict]:
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append(
            {"device": p.device, "description": p.description or "", "hwid": p.hwid or ""}
        )
    return ports
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
pytest tests/test_integration_serial.py tests/test_integration_http.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add pymice/backend/tests/test_integration_serial.py pymice/backend/tests/test_integration_http.py pymice/backend/app/services/integrations.py
git commit -m "feat(experiment): integration adapters (serial, http) with LAN whitelist"
```

---

## Task 6: LiveExperiment skeleton (no loop yet)

**Files:**
- Create: `pymice/backend/app/processing/live_experiment.py`

This task builds the class shell, file I/O, and start/stop lifecycle. The actual capture/detect loop body comes in Task 7 (so we can test it in isolation).

- [ ] **Step 1: Implement skeleton**

Create `pymice/backend/app/processing/live_experiment.py`:

```python
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

from app.models.schemas import ExperimentStartRequest, ROIPreset, TriggerRule
from app.processing.trigger_evaluator import TriggerEvaluator
from app.services.event_bus import EventBus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        base_dir: str = "temp/experiments",
    ):
        """
        stream_provider:           callable that returns the current cv2.VideoCapture or None
        annotated_frame_setter:    callable(np.ndarray) → stores frame in shared buffer
        """
        self.request = request
        self._bus = event_bus
        self._stream_provider = stream_provider
        self._annotated_frame_setter = annotated_frame_setter
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
        """Implemented in Task 7."""
        raise NotImplementedError
```

- [ ] **Step 2: Smoke-test import**

```bash
python -c "from app.processing.live_experiment import LiveExperiment; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add pymice/backend/app/processing/live_experiment.py
git commit -m "feat(experiment): LiveExperiment skeleton (lifecycle, artifacts, mutators)"
```

---

## Task 7: LiveExperiment loop body + integration test

**Files:**
- Modify: `pymice/backend/app/processing/live_experiment.py:_loop`
- Create: `pymice/backend/tests/test_live_experiment_loop.py`

- [ ] **Step 1: Write failing integration test**

Create `pymice/backend/tests/test_live_experiment_loop.py`:

```python
"""Integration test for the LiveExperiment loop.

VideoCapture and YOLO model are both replaced with fakes that produce
deterministic frames and detections. We assert on the on-disk artifacts.
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.models.schemas import (
    ExperimentStartRequest,
    RectangleROI,
    ROIPreset,
)
from app.processing.live_experiment import LiveExperiment
from app.services.event_bus import EventBus


class FakeCapture:
    def __init__(self, frames, width=320, height=240, fps=30.0):
        self._frames = frames
        self._i = 0
        self._w = width
        self._h = height
        self._fps = fps

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self._w
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self._h
        if prop == cv2.CAP_PROP_FPS:
            return self._fps
        return 0.0

    def read(self):
        if self._i >= len(self._frames):
            return False, None
        frame = self._frames[self._i]
        self._i += 1
        return True, frame


class FakeYOLO:
    """Returns a detection at (centroid_xs[i], centroid_ys[i]) for frame i."""

    def __init__(self, xs, ys):
        self._xs = xs
        self._ys = ys
        self._i = 0
        self.names = {0: "mouse"}

    def predict(self, frame, **kwargs):
        i = min(self._i, len(self._xs) - 1)
        x, y = self._xs[i], self._ys[i]
        self._i += 1

        # Build a minimal Ultralytics-like result
        class Box:
            def __init__(self, xyxy, conf, cls):
                self.xyxy = np.array([xyxy])
                self.conf = np.array([conf])
                self.cls = np.array([cls])

        class Result:
            def __init__(self, box):
                self.boxes = [box]

        bbox = (x - 5, y - 5, x + 5, y + 5)
        return [Result(Box(bbox, 0.9, 0))]


def _make_request(tmp_path):
    rois = ROIPreset(
        preset_name="t",
        description="",
        timestamp="2026-05-15",
        frame_width=320,
        frame_height=240,
        rois=[
            RectangleROI(
                roi_type="Rectangle",
                center_x=80, center_y=120, width=80, height=120,  # left half
            ),
            RectangleROI(
                roi_type="Rectangle",
                center_x=240, center_y=120, width=80, height=120,  # right half
            ),
        ],
    )
    return ExperimentStartRequest(
        device_id=0,
        model_name="dummy.pt",
        rois=rois,
        confidence_threshold=0.5,
        iou_threshold=0.5,
        max_consecutive_drops=3,
    )


@pytest.mark.asyncio
async def test_loop_writes_tracking_and_roi_events(tmp_path):
    # 6 frames: centroid moves left → left → right → right → left → left
    frames = [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(6)]
    xs = [50, 60, 240, 250, 60, 70]
    ys = [120, 120, 120, 120, 120, 120]

    bus = EventBus()
    fake_cap = FakeCapture(frames)
    annotated = {"frame": None}

    fake_model = FakeYOLO(xs, ys)

    with patch("app.processing.live_experiment._load_yolo_model", return_value=fake_model):
        exp = LiveExperiment(
            request=_make_request(tmp_path),
            event_bus=bus,
            stream_provider=lambda: fake_cap,
            annotated_frame_setter=lambda f: annotated.__setitem__("frame", f),
            base_dir=str(tmp_path / "experiments"),
        )
        exp.start()
        # Wait for all 6 frames + a couple of stall reads to trigger stream_lost
        time.sleep(2.0)
        exp.stop("test")

    tracking_lines = Path(exp._artifacts.tracking_jsonl).read_text().splitlines()
    events_lines = Path(exp._artifacts.events_jsonl).read_text().splitlines()

    assert len(tracking_lines) >= 6
    types = [json.loads(l).get("type") for l in events_lines]
    assert "started" in types
    assert types.count("roi_entry") >= 2
    assert types.count("roi_exit") >= 2
    assert "stopped" in types

    # Raw video exists with non-zero size
    assert os.path.getsize(exp._artifacts.raw_video) > 0


@pytest.mark.asyncio
async def test_loop_auto_stops_on_consecutive_drops(tmp_path):
    frames = []  # all reads fail immediately
    bus = EventBus()
    fake_cap = FakeCapture(frames)
    annotated = {"frame": None}
    fake_model = FakeYOLO([0], [0])

    with patch("app.processing.live_experiment._load_yolo_model", return_value=fake_model):
        exp = LiveExperiment(
            request=_make_request(tmp_path),
            event_bus=bus,
            stream_provider=lambda: fake_cap,
            annotated_frame_setter=lambda f: annotated.__setitem__("frame", f),
            base_dir=str(tmp_path / "experiments"),
        )
        exp.start()
        time.sleep(1.0)

    events = [json.loads(l) for l in Path(exp._artifacts.events_jsonl).read_text().splitlines()]
    stopped = [e for e in events if e.get("type") == "stopped"]
    assert stopped
    assert stopped[-1]["reason"] == "stream_lost"
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/test_live_experiment_loop.py -v
```

Expected: NotImplementedError when starting (the loop body is the `raise NotImplementedError` from Task 6).

- [ ] **Step 3: Replace `_loop()` body in live_experiment.py**

In `pymice/backend/app/processing/live_experiment.py`, remove the `raise NotImplementedError` and add at the top of the file:

```python
import numpy as np
from app.processing.tracking import get_roi_containing_point, draw_rois
```

Then add this helper at module level (above the class):

```python
def _load_yolo_model(model_path: str):
    """Indirected for testability."""
    from ultralytics import YOLO
    return YOLO(model_path)


def _best_detection(results) -> Optional[tuple]:
    """Pick the highest-confidence box from Ultralytics results.
    Returns (centroid_x, centroid_y, bbox_xyxy, confidence) or None.
    """
    if not results:
        return None
    r = results[0]
    if not getattr(r, "boxes", None):
        return None
    boxes = r.boxes
    if len(boxes) == 0:
        return None
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
```

Replace the stub `_loop` method body with:

```python
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

            # ROI eval
            active_roi: Optional[int] = None
            with self._rois_lock:
                rois = list(self._rois)
                roi_names = list(self._roi_names)
            if not self._paused_roi_eval and centroid is not None:
                active_roi = get_roi_containing_point(centroid, rois)

            # ROI delta events
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

            # Triggers (action dispatch is handled by the router/WS layer in a future
            # task; for now we just emit `trigger` events with rule + skipped state)
            with self._triggers_lock:
                fires = self._evaluator.evaluate(events_this_frame)
            for fire in fires:
                self._emit({"type": "trigger", **fire})

            # Tracking JSONL
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

            # Write raw frame, then annotate copy for display
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

            # Periodic tick
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
```

- [ ] **Step 4: Run test, confirm pass**

```bash
pytest tests/test_live_experiment_loop.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pymice/backend/app/processing/live_experiment.py pymice/backend/tests/test_live_experiment_loop.py
git commit -m "feat(experiment): LiveExperiment loop (YOLO + ROI events + JSONL + raw mp4)"
```

---

## Task 8: Trigger action execution

The loop currently emits `trigger` events but does not call SerialAdapter/HttpAdapter. This task wires up action execution by passing an action-dispatch callable into LiveExperiment.

**Files:**
- Modify: `pymice/backend/app/processing/live_experiment.py`

- [ ] **Step 1: Add action_dispatcher parameter**

In `pymice/backend/app/processing/live_experiment.py`, in `LiveExperiment.__init__`, after `annotated_frame_setter`, add `action_dispatcher=None,` parameter and store as `self._dispatch_action = action_dispatcher or (lambda rule, evt: {"ok": True, "skipped": "no_dispatcher"})`.

The dispatcher signature: `dispatch(rule_dict, event_dict) -> dict` (sync, called from the loop thread; integrations should schedule asyncio work themselves via `asyncio.run_coroutine_threadsafe` — see Task 10).

- [ ] **Step 2: Use the dispatcher in the loop**

In `_loop`, replace the `for fire in fires:` block with:

```python
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
```

- [ ] **Step 3: Run existing tests**

```bash
pytest tests/test_live_experiment_loop.py -v
```

Expected: still 2 passed (no dispatcher → default no-op).

- [ ] **Step 4: Commit**

```bash
git add pymice/backend/app/processing/live_experiment.py
git commit -m "feat(experiment): pluggable action dispatcher for triggers"
```

---

## Task 9: Camera router — serve annotated frame when present

**Files:**
- Modify: `pymice/backend/app/routers/camera.py`

- [ ] **Step 1: Update camera_state and /frame handler**

In `pymice/backend/app/routers/camera.py`, change `camera_state` initializer to include `"annotated_frame": None` and `"annotated_lock": threading.Lock()`.

Add at top:

```python
import threading
```

Update `camera_state`:

```python
camera_state = {
    "stream": None,
    "recording": None,
    "device_id": None,
    "annotated_frame": None,
    "annotated_lock": threading.Lock(),
}
```

Replace the `get_frame` body so it prefers the annotated frame when set:

```python
@router.get("/frame")
async def get_frame():
    """Get current frame from camera stream.

    If a LiveExperiment is running and has injected an annotated frame,
    we serve that instead of the raw capture so the UI shows overlays
    without a separate endpoint.
    """
    annotated = None
    with camera_state["annotated_lock"]:
        if camera_state["annotated_frame"] is not None:
            annotated = camera_state["annotated_frame"].copy()

    if annotated is not None:
        _, buffer = cv2.imencode(".jpg", annotated)
        return StreamingResponse(io.BytesIO(buffer.tobytes()), media_type="image/jpeg")

    if not camera_state["stream"]:
        raise HTTPException(status_code=400, detail="No active stream")

    ret, frame = camera_state["stream"].read()
    if not ret:
        raise HTTPException(status_code=500, detail="Failed to read frame")

    if camera_state["recording"] and camera_state["recording"]["writer"]:
        camera_state["recording"]["writer"].write(frame)

    _, buffer = cv2.imencode(".jpg", frame)
    return StreamingResponse(io.BytesIO(buffer.tobytes()), media_type="image/jpeg")
```

Also update `stop_stream` to clear the annotated frame:

```python
@router.post("/stream/stop")
async def stop_stream():
    """Stop camera stream"""
    if camera_state["stream"]:
        camera_state["stream"].release()
        camera_state["stream"] = None
    with camera_state["annotated_lock"]:
        camera_state["annotated_frame"] = None

    return ApiResponse(success=True, data={"message": "Stream stopped"})
```

- [ ] **Step 2: Smoke-test backend boots**

```bash
cd pymice/backend
uvicorn app.main:app --port 8765 &
sleep 2
curl -s http://localhost:8765/health
kill %1
```

Expected: `{"status":"healthy"}`.

- [ ] **Step 3: Commit**

```bash
git add pymice/backend/app/routers/camera.py
git commit -m "feat(camera): /frame serves annotated buffer when LiveExperiment is running"
```

---

## Task 10: Experiment router (REST + WS) and singleton state

**Files:**
- Create: `pymice/backend/app/routers/experiment.py`

- [ ] **Step 1: Create the router**

Create `pymice/backend/app/routers/experiment.py`:

```python
"""Experiment Recording API.

Owns:
  - LiveExperiment singleton (one per process)
  - REST endpoints for lifecycle, integrations, triggers, ROI updates
  - WebSocket /events channel
  - Action dispatcher that bridges trigger fires → integration adapters
"""

import asyncio
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

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
_adapters: Dict[str, object] = {}  # integration_id → adapter


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


_main_loop_ref: Dict[str, Optional[asyncio.AbstractEventLoop]] = {"loop": None}


@router.on_event("startup")
async def _capture_main_loop():
    _main_loop_ref["loop"] = asyncio.get_event_loop()


# --- experiment lifecycle ---

@router.post("/start")
async def start_experiment(request: ExperimentStartRequest):
    if _experiment_state["current"] is not None and _experiment_state["current"]._state == "running":
        raise HTTPException(status_code=409, detail="Experiment already running")
    if camera_state.get("stream") is None:
        raise HTTPException(status_code=409, detail="No active camera stream — start stream first")

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
    # Clear annotated frame so /camera/frame falls back to raw
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


# --- artifact download (server local path → file response) ---

from fastapi.responses import FileResponse


@router.get("/artifacts/{exp_id}/{artifact}")
async def artifact_download(exp_id: str, artifact: str):
    allowed = {"raw.mp4", "tracking.jsonl", "events.jsonl", "metadata.json"}
    if artifact not in allowed:
        raise HTTPException(status_code=400, detail="invalid artifact")
    path = os.path.join("temp/experiments", exp_id, artifact)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, filename=f"{exp_id}_{artifact}")
```

- [ ] **Step 2: Smoke-test imports**

```bash
python -c "from app.routers.experiment import router; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add pymice/backend/app/routers/experiment.py
git commit -m "feat(experiment): /api/experiment router (REST + WS + integrations + triggers)"
```

---

## Task 11: Wire router into main.py; protect experiments dir

**Files:**
- Modify: `pymice/backend/app/main.py`

- [ ] **Step 1: Import experiment router**

In `pymice/backend/app/main.py`, change the import line:

```python
from app.routers import camera, video, tracking, roi, analysis, system, experiment
```

- [ ] **Step 2: Mount the router**

After the existing `app.include_router(system.router, ...)` line, add:

```python
app.include_router(experiment.router, prefix="/api/experiment", tags=["Experiment"])
```

- [ ] **Step 3: Protect temp/experiments and temp/integrations.json from cleanup**

The cleanup function uses an explicit list of dirs — `temp/experiments` and `temp/integrations.json` are not in it, so they're already preserved. But add a comment so a future engineer doesn't add them by reflex. Locate the `temp_dirs` list and replace with:

```python
    # NOTE: temp/experiments/ and temp/integrations.json are deliberately NOT cleaned —
    # they hold user data (recordings, hardware bindings) that must survive restarts.
    temp_dirs = [
        "temp/videos",
        "temp/tracking",
        "temp/analysis",
        # "temp/models",
        "temp/roi_templates",
    ]
```

- [ ] **Step 4: Mark orphan experiments as crashed on startup**

In `startup_event`, after the `os.makedirs(...)` lines, append:

```python
    os.makedirs("temp/experiments", exist_ok=True)
    _mark_orphan_experiments()
```

And add this function above `startup_event`:

```python
def _mark_orphan_experiments():
    """If a previous run died, any experiment still marked 'running' in
    metadata.json is now an orphan — flag it as crashed."""
    import json
    base = "temp/experiments"
    if not os.path.isdir(base):
        return
    for entry in os.listdir(base):
        meta_path = os.path.join(base, entry, "metadata.json")
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            if meta.get("state") == "running":
                meta["state"] = "crashed"
                with open(meta_path, "w") as f:
                    json.dump(meta, f, indent=2)
                print(f"⚠️  Marked orphan experiment as crashed: {entry}")
        except Exception as e:
            print(f"   Could not check {entry}: {e}")
```

- [ ] **Step 5: Smoke-test boot**

```bash
cd pymice/backend
uvicorn app.main:app --port 8765 &
sleep 2
curl -s http://localhost:8765/api/experiment/status
kill %1
```

Expected: `{"success":true,"data":{"state":"idle"},"error":null}`.

- [ ] **Step 6: Commit**

```bash
git add pymice/backend/app/main.py
git commit -m "feat(experiment): mount router; orphan detection; protect temp/experiments"
```

---

## Task 12: Add frontend types and API client

**Files:**
- Modify: `pymice/frontend/src/types/index.ts`
- Modify: `pymice/frontend/src/services/api.ts`

- [ ] **Step 1: Add types**

Open `pymice/frontend/src/types/index.ts` and append:

```typescript
// --- Experiment Recording ---

export type SerialPort = { device: string; description: string; hwid: string }

export type IntegrationKind = 'serial' | 'http'

export interface IntegrationConfigSerial {
  port: string
  baud: number
  newline: string
}

export interface IntegrationConfigHttp {
  base_url: string
  default_method: 'GET' | 'POST' | 'PUT'
  default_timeout_sec: number
  headers: Record<string, string>
}

export interface Integration {
  id: string
  name: string
  kind: IntegrationKind
  config: IntegrationConfigSerial | IntegrationConfigHttp
}

export interface TriggerMatch {
  event_type: 'roi_entry' | 'roi_exit' | 'tick' | 'frame_drop'
  roi_name?: string | null
  min_dwell_sec?: number | null
  cooldown_sec?: number | null
}

export interface TriggerAction {
  integration_id?: string | null
  kind: 'integration' | 'log'
  payload?: string | Record<string, unknown> | null
  label?: string | null
  timeout_sec?: number
}

export interface TriggerRule {
  id: string
  name: string
  match: TriggerMatch
  action: TriggerAction
}

export interface ExperimentStartRequest {
  device_id: number
  model_name: string
  rois: ROIPreset
  confidence_threshold?: number
  iou_threshold?: number
  inference_size?: number
  fps_target?: number | null
  max_consecutive_drops?: number
  triggers?: TriggerRule[]
}

export interface ExperimentStatus {
  exp_id?: string | null
  state: 'idle' | 'running' | 'stopped' | 'crashed'
  started_at?: string | null
  frames_processed: number
  fps_actual: number
  detections: number
  events_emitted: number
  last_active_roi?: number | null
}

export interface ExperimentEvent {
  type: string
  frame_idx?: number
  t?: number
  // additional fields per type
  [k: string]: unknown
}
```

- [ ] **Step 2: Add experimentApi**

Open `pymice/frontend/src/services/api.ts` and append (before the final `export default api` if present, otherwise at the end):

```typescript
import type {
  Integration,
  TriggerRule,
  ExperimentStartRequest,
  ExperimentStatus,
  SerialPort,
} from '@/types'

export const experimentApi = {
  start: (req: ExperimentStartRequest) =>
    api.post<ApiResponse<{ exp_id: string; ws_url: string }>>('/experiment/start', req),
  stop: () => api.post<ApiResponse<{ exp_id: string; artifacts: Record<string, string> }>>('/experiment/stop'),
  status: () => api.get<ApiResponse<ExperimentStatus>>('/experiment/status'),

  listIntegrations: () =>
    api.get<ApiResponse<{ integrations: Integration[] }>>('/experiment/integrations'),
  createIntegration: (i: Integration) =>
    api.post<ApiResponse<Integration>>('/experiment/integrations', i),
  deleteIntegration: (id: string, force = false) =>
    api.delete<ApiResponse<{ deleted: string }>>(`/experiment/integrations/${id}${force ? '?force=true' : ''}`),
  testIntegration: (id: string) =>
    api.post<ApiResponse<{ ok: boolean; status_code?: number; latency_ms?: number; error?: string }>>(`/experiment/integrations/${id}/test`),
  listSerialPorts: () =>
    api.get<ApiResponse<{ ports: SerialPort[] }>>('/experiment/serial-ports'),

  listTriggers: () =>
    api.get<ApiResponse<{ triggers: TriggerRule[] }>>('/experiment/triggers'),
  createTrigger: (r: TriggerRule) =>
    api.post<ApiResponse<TriggerRule>>('/experiment/triggers', r),
  deleteTrigger: (id: string) =>
    api.delete<ApiResponse<{ deleted: string }>>(`/experiment/triggers/${id}`),

  updateRois: (preset: import('@/types').ROIPreset) =>
    api.post<ApiResponse<{ updated: boolean }>>('/experiment/rois', preset),
  pauseRoiEval: (paused: boolean) =>
    api.post<ApiResponse<{ paused: boolean }>>(`/experiment/rois/pause-eval?paused=${paused}`),

  artifactUrl: (expId: string, artifact: 'raw.mp4' | 'tracking.jsonl' | 'events.jsonl' | 'metadata.json') =>
    `/api/experiment/artifacts/${expId}/${artifact}`,

  /** Open a WebSocket on /api/experiment/events. Caller manages lifecycle. */
  subscribeEvents: (onEvent: (e: import('@/types').ExperimentEvent) => void, onClose?: () => void): WebSocket => {
    // Vite dev server proxies HTTP /api/* → :8765; WS needs explicit proxy or absolute URL.
    // We use the same host but ws:// protocol matching the page.
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/api/experiment/events`)
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data) as import('@/types').ExperimentEvent
        onEvent(data)
      } catch {
        // ignore malformed
      }
    }
    if (onClose) ws.onclose = onClose
    return ws
  },
}
```

- [ ] **Step 3: Update Vite proxy to forward WebSockets**

Open `pymice/frontend/vite.config.ts`. In the `server.proxy['/api']` block, set `ws: true`. If the file currently looks like:

```typescript
proxy: { '/api': { target: 'http://localhost:8765', changeOrigin: true } }
```

change to:

```typescript
proxy: { '/api': { target: 'http://localhost:8765', changeOrigin: true, ws: true } }
```

- [ ] **Step 4: Typecheck**

```bash
cd pymice/frontend
npm run build
```

Expected: `tsc --noEmit` passes, `vite build` succeeds.

- [ ] **Step 5: Commit**

```bash
git add pymice/frontend/src/types/index.ts pymice/frontend/src/services/api.ts pymice/frontend/vite.config.ts
git commit -m "feat(experiment): frontend types, experimentApi, WS proxy"
```

---

## Task 13: Extract ROICanvas shared component

This is a refactor — extract the ROI drawing canvas + handlers from `TrackingTab.tsx` into a controlled component, then update TrackingTab to consume it.

**Files:**
- Create: `pymice/frontend/src/components/ROICanvas.tsx`
- Modify: `pymice/frontend/src/pages/TrackingTab.tsx`

Because TrackingTab is 1983 lines, this is done in two passes: first create the component matching the existing API, then update TrackingTab to use it without behavior changes.

- [ ] **Step 1: Create ROICanvas**

Read TrackingTab.tsx and find the ROI canvas section (around the mouse handlers `handleMouseDown`, `handleMouseMove`, `handleMouseUp`, the `currentROIType` state, `polygonPoints`, and the canvas element rendering).

Create `pymice/frontend/src/components/ROICanvas.tsx`:

```typescript
import { useEffect, useRef, useState } from 'react'
import type { ROI, ROIPreset } from '@/types'
import { drawROI } from '@/utils/canvas'

export type ROIToolType =
  | 'Rectangle'
  | 'Circle'
  | 'Polygon'
  | 'OpenFieldRectangle'
  | 'OpenFieldCircle'

export type ROICanvasMode = 'edit' | 'view-only' | 'live-overlay'

interface ROICanvasProps {
  width: number
  height: number
  rois: ROI[]
  onRoisChange?: (rois: ROI[]) => void
  mode: ROICanvasMode
  activeRoiIndex?: number | null
  /** Background image to render under the ROIs. Pass null for a black canvas. */
  backgroundFrame?: HTMLImageElement | HTMLCanvasElement | null
  /** Optional tool selection — only used in edit mode. */
  tool?: ROIToolType
  onToolChange?: (tool: ROIToolType) => void
  colors?: string[]
}

const DEFAULT_COLORS = ['#ef4444', '#22c55e', '#3b82f6', '#f59e0b', '#a855f7', '#06b6d4']

export default function ROICanvas({
  width,
  height,
  rois,
  onRoisChange,
  mode,
  activeRoiIndex = null,
  backgroundFrame = null,
  tool = 'Rectangle',
  colors = DEFAULT_COLORS,
}: ROICanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null)
  const [polygonPoints, setPolygonPoints] = useState<{ x: number; y: number }[]>([])
  const [hoverPoint, setHoverPoint] = useState<{ x: number; y: number } | null>(null)

  const editable = mode === 'edit'

  const repaint = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width = width
    canvas.height = height
    ctx.clearRect(0, 0, width, height)

    if (backgroundFrame) {
      ctx.drawImage(backgroundFrame, 0, 0, width, height)
    } else {
      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, width, height)
    }

    rois.forEach((roi, idx) => {
      const color = colors[idx % colors.length]
      const highlight = mode === 'live-overlay' && idx === activeRoiIndex
      drawROI(ctx, roi, color, highlight ? 4 : 2, true, highlight ? 0.3 : 0.1)
    })

    // In-progress drawing preview
    if (editable && isDrawing && drawStart && hoverPoint) {
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 2
      if (tool === 'Rectangle' || tool === 'OpenFieldRectangle') {
        ctx.strokeRect(
          drawStart.x,
          drawStart.y,
          hoverPoint.x - drawStart.x,
          hoverPoint.y - drawStart.y,
        )
      } else if (tool === 'Circle' || tool === 'OpenFieldCircle') {
        const r = Math.hypot(hoverPoint.x - drawStart.x, hoverPoint.y - drawStart.y)
        ctx.beginPath()
        ctx.arc(drawStart.x, drawStart.y, r, 0, Math.PI * 2)
        ctx.stroke()
      }
    }
    if (editable && tool === 'Polygon' && polygonPoints.length > 0) {
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(polygonPoints[0].x, polygonPoints[0].y)
      polygonPoints.slice(1).forEach((p) => ctx.lineTo(p.x, p.y))
      if (hoverPoint) ctx.lineTo(hoverPoint.x, hoverPoint.y)
      ctx.stroke()
      polygonPoints.forEach((p) => {
        ctx.fillStyle = '#fbbf24'
        ctx.beginPath()
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2)
        ctx.fill()
      })
    }
  }

  useEffect(() => {
    repaint()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rois, activeRoiIndex, backgroundFrame, isDrawing, drawStart, hoverPoint, polygonPoints, tool])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!editable) return
      if (e.key === 'Escape' && tool === 'Polygon' && polygonPoints.length > 0) {
        setPolygonPoints([])
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [editable, tool, polygonPoints])

  const toCanvas = (e: React.MouseEvent) => {
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width) * width,
      y: ((e.clientY - rect.top) / rect.height) * height,
    }
  }

  const onMouseDown = (e: React.MouseEvent) => {
    if (!editable) return
    const p = toCanvas(e)
    if (tool === 'Polygon') {
      if (polygonPoints.length >= 3) {
        // Check if click is near the first vertex → close
        const first = polygonPoints[0]
        if (Math.hypot(first.x - p.x, first.y - p.y) < 10) {
          const cx = polygonPoints.reduce((s, pt) => s + pt.x, 0) / polygonPoints.length
          const cy = polygonPoints.reduce((s, pt) => s + pt.y, 0) / polygonPoints.length
          const newRoi: ROI = {
            roi_type: 'Polygon',
            center_x: cx,
            center_y: cy,
            vertices: polygonPoints.map((pt) => [pt.x, pt.y]) as number[][],
          } as ROI
          onRoisChange?.([...rois, newRoi])
          setPolygonPoints([])
          return
        }
      }
      setPolygonPoints([...polygonPoints, p])
      return
    }
    setIsDrawing(true)
    setDrawStart(p)
  }

  const onMouseMove = (e: React.MouseEvent) => {
    if (!editable) return
    setHoverPoint(toCanvas(e))
  }

  const onMouseUp = (e: React.MouseEvent) => {
    if (!editable || !isDrawing || !drawStart) return
    setIsDrawing(false)
    const p = toCanvas(e)
    let newRoi: ROI | null = null
    if (tool === 'Rectangle' || tool === 'OpenFieldRectangle') {
      const w = Math.abs(p.x - drawStart.x)
      const h = Math.abs(p.y - drawStart.y)
      if (w < 5 || h < 5) {
        setDrawStart(null)
        return
      }
      newRoi = {
        roi_type: 'Rectangle',
        center_x: (drawStart.x + p.x) / 2,
        center_y: (drawStart.y + p.y) / 2,
        width: w,
        height: h,
      } as ROI
    } else if (tool === 'Circle' || tool === 'OpenFieldCircle') {
      const r = Math.hypot(p.x - drawStart.x, p.y - drawStart.y)
      if (r < 5) {
        setDrawStart(null)
        return
      }
      newRoi = {
        roi_type: 'Circle',
        center_x: drawStart.x,
        center_y: drawStart.y,
        radius: r,
      } as ROI
    }
    if (newRoi) onRoisChange?.([...rois, newRoi])
    setDrawStart(null)
  }

  return (
    <canvas
      ref={canvasRef}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      style={{ width: '100%', maxWidth: width, cursor: editable ? 'crosshair' : 'default' }}
      className="bg-black rounded-lg border border-gray-300 dark:border-gray-700"
    />
  )
}
```

- [ ] **Step 2: Typecheck**

```bash
cd pymice/frontend
npm run build
```

Expected: passes.

- [ ] **Step 3: Refactor TrackingTab to consume ROICanvas**

The original TrackingTab.tsx has its ROI drawing logic inline. Locate the section that:
- Defines `currentROIType` state, `polygonPoints` state, `drawStart`, `isDrawing`
- Defines `handleMouseDown`, `handleMouseMove`, `handleMouseUp`
- Renders `<canvas ref={canvasRef} onMouseDown={...} onMouseMove={...} onMouseUp={...} />`

Replace that block with:

```tsx
<ROICanvas
  width={videoInfo?.width ?? 640}
  height={videoInfo?.height ?? 480}
  rois={rois}
  onRoisChange={setRois}
  mode="edit"
  tool={currentROIType}
  backgroundFrame={currentFrameImage}
/>
```

Remove the local mouse handlers and the local drawing helper code that's now in ROICanvas. Keep `currentROIType` state for the tool toolbar; pass it as `tool`.

Add at top of TrackingTab.tsx:

```tsx
import ROICanvas from '@/components/ROICanvas'
```

This is a significant edit; verify after each pass:

```bash
npm run lint
npm run build
```

Both must pass before continuing.

- [ ] **Step 4: Manual sanity check**

```bash
cd ../..
./pymice/run.sh start
```

Open `http://localhost:5765`, go to Tracking tab, upload a small video, draw a rectangle + circle + polygon, save as template. Verify drawing still works exactly as before.

```bash
./pymice/run.sh stop
```

- [ ] **Step 5: Commit**

```bash
git add pymice/frontend/src/components/ROICanvas.tsx pymice/frontend/src/pages/TrackingTab.tsx
git commit -m "refactor(frontend): extract ROICanvas; TrackingTab uses shared component"
```

---

## Task 14: Build ExperimentRecordingTab (replaces CameraTab)

**Files:**
- Create: `pymice/frontend/src/pages/ExperimentRecordingTab.tsx`
- Delete: `pymice/frontend/src/pages/CameraTab.tsx`
- Modify: `pymice/frontend/src/App.tsx`

- [ ] **Step 1: Create ExperimentRecordingTab.tsx**

This file inherits the stream/recording controls from CameraTab and adds Setup → Live → Done state. It composes three sub-panels (built in later tasks). For this task we ship a minimal working version: stream + ROI drawing + Start/Stop + frame display.

Create `pymice/frontend/src/pages/ExperimentRecordingTab.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import { Camera, Video, Square, Circle, Play, StopCircle, Download } from 'lucide-react'
import { cameraApi, experimentApi, trackingApi } from '@/services/api'
import ROICanvas from '@/components/ROICanvas'
import type { ROI, ROIPreset, ExperimentEvent } from '@/types'
import IntegrationsPanel from '@/components/IntegrationsPanel'
import TriggersPanel from '@/components/TriggersPanel'
import EventLogPanel from '@/components/EventLogPanel'

interface Props {
  onTrackingStateChange?: (isActive: boolean) => void
}

type View = 'setup' | 'live' | 'done'

export default function ExperimentRecordingTab({ onTrackingStateChange }: Props = {}) {
  const [view, setView] = useState<View>('setup')
  const [devices, setDevices] = useState<number[]>([])
  const [selectedDevice, setSelectedDevice] = useState<number>(0)
  const [resolution, setResolution] = useState({ width: 640, height: 480 })
  const [isStreaming, setIsStreaming] = useState(false)
  const [rois, setRois] = useState<ROI[]>([])
  const [tool, setTool] = useState<'Rectangle' | 'Circle' | 'Polygon'>('Rectangle')

  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('')

  const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null)
  const pollRef = useRef<number | null>(null)

  const [expId, setExpId] = useState<string | null>(null)
  const [activeRoi, setActiveRoi] = useState<number | null>(null)
  const [events, setEvents] = useState<ExperimentEvent[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const [artifacts, setArtifacts] = useState<Record<string, string> | null>(null)

  useEffect(() => {
    onTrackingStateChange?.(view === 'live')
  }, [view, onTrackingStateChange])

  useEffect(() => {
    cameraApi.listDevices().then((r) => {
      const list = Array.isArray(r.data.data) ? r.data.data : r.data.data?.devices || []
      setDevices(list)
      if (list.length > 0) setSelectedDevice(list[0])
    })
    trackingApi.listModels().then((r) => {
      const list = r.data.data || []
      setModels(list)
      if (list.length > 0) setSelectedModel(list[0])
    })
  }, [])

  const pollFrame = async () => {
    try {
      const r = await cameraApi.getFrame()
      const url = URL.createObjectURL(r.data)
      const img = new Image()
      img.onload = () => {
        setBgImage(img)
        URL.revokeObjectURL(url)
      }
      img.src = url
    } catch {
      /* ignore transient errors */
    }
  }

  const startStream = async () => {
    await cameraApi.startStream(selectedDevice)
    setIsStreaming(true)
    pollRef.current = window.setInterval(pollFrame, 33)
  }

  const stopStream = async () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    await cameraApi.stopStream()
    setIsStreaming(false)
    setBgImage(null)
  }

  const startExperiment = async () => {
    const preset: ROIPreset = {
      preset_name: 'live',
      description: 'Created in Experiment Recording',
      timestamp: new Date().toISOString(),
      frame_width: resolution.width,
      frame_height: resolution.height,
      rois,
    }
    const r = await experimentApi.start({
      device_id: selectedDevice,
      model_name: selectedModel,
      rois: preset,
      confidence_threshold: 0.5,
      iou_threshold: 0.5,
      inference_size: 640,
      triggers: [],
    })
    if (!r.data.success || !r.data.data) {
      alert(`Failed to start experiment: ${r.data.error}`)
      return
    }
    setExpId(r.data.data.exp_id)
    setView('live')
    setEvents([])

    wsRef.current = experimentApi.subscribeEvents(
      (evt) => {
        setEvents((prev) => [...prev.slice(-200), evt])
        if (evt.type === 'roi_entry') setActiveRoi(evt.roi_index as number)
        if (evt.type === 'roi_exit') setActiveRoi(null)
        if (evt.type === 'tick' && typeof evt.active_roi !== 'undefined') {
          setActiveRoi((evt.active_roi as number | null) ?? null)
        }
        if (evt.type === 'stopped') {
          setView('done')
        }
      },
      () => { /* ws closed */ },
    )
  }

  const stopExperiment = async () => {
    const r = await experimentApi.stop()
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (r.data.success && r.data.data) {
      setArtifacts(r.data.data.artifacts)
    }
    setView('done')
  }

  const reset = async () => {
    setExpId(null)
    setArtifacts(null)
    setEvents([])
    setActiveRoi(null)
    setView('setup')
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Camera className="w-5 h-5 text-primary-500" />
          Experiment Recording
        </h2>

        {/* Stream controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium mb-1">Camera Device</label>
            <select
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(Number(e.target.value))}
              disabled={isStreaming || view === 'live'}
              className="w-full bg-white dark:bg-gray-700 border rounded px-3 py-2"
            >
              {devices.map((d) => (
                <option key={d} value={d}>Camera {d}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">YOLO Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={view === 'live'}
              className="w-full bg-white dark:bg-gray-700 border rounded px-3 py-2"
            >
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={isStreaming ? stopStream : startStream}
              disabled={view === 'live'}
              className={`w-full px-4 py-2 rounded text-white ${
                isStreaming ? 'bg-red-600' : 'bg-primary-600'
              } disabled:opacity-50`}
            >
              {isStreaming ? (<><Square className="inline w-4 h-4 mr-2" /> Stop Stream</>) :
                            (<><Circle className="inline w-4 h-4 mr-2" /> Start Stream</>)}
            </button>
          </div>
        </div>

        {/* Tool selector (only in setup) */}
        {view === 'setup' && isStreaming && (
          <div className="flex gap-2 mb-3">
            {(['Rectangle', 'Circle', 'Polygon'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTool(t)}
                className={`px-3 py-1 rounded text-sm border ${
                  tool === t ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-700'
                }`}
              >
                {t}
              </button>
            ))}
            <button onClick={() => setRois([])} className="px-3 py-1 rounded text-sm border ml-auto">
              Clear ROIs
            </button>
          </div>
        )}

        {/* Canvas */}
        <ROICanvas
          width={resolution.width}
          height={resolution.height}
          rois={rois}
          onRoisChange={setRois}
          mode={view === 'live' ? 'live-overlay' : view === 'done' ? 'view-only' : 'edit'}
          activeRoiIndex={activeRoi}
          backgroundFrame={bgImage}
          tool={tool}
        />

        {/* Start/Stop experiment */}
        <div className="mt-4 flex gap-3">
          {view === 'setup' && (
            <button
              onClick={startExperiment}
              disabled={!isStreaming || rois.length === 0 || !selectedModel}
              className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-2 rounded flex items-center gap-2"
            >
              <Play className="w-4 h-4" /> Start Experiment
            </button>
          )}
          {view === 'live' && (
            <button
              onClick={stopExperiment}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded flex items-center gap-2"
            >
              <StopCircle className="w-4 h-4" /> Stop Experiment
            </button>
          )}
          {view === 'done' && (
            <button onClick={reset} className="bg-primary-600 text-white px-4 py-2 rounded">
              New Experiment
            </button>
          )}
        </div>

        {/* Artifacts (done) */}
        {view === 'done' && artifacts && expId && (
          <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded">
            <h3 className="font-medium mb-2">Artifacts</h3>
            <ul className="space-y-1 text-sm">
              {(['raw.mp4', 'tracking.jsonl', 'events.jsonl', 'metadata.json'] as const).map((a) => (
                <li key={a}>
                  <a
                    href={experimentApi.artifactUrl(expId, a)}
                    download
                    className="text-primary-600 hover:underline inline-flex items-center gap-1"
                  >
                    <Download className="w-3 h-3" /> {a}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Side panels — only in setup (you wire them in next tasks) */}
      {view === 'setup' && (
        <>
          <IntegrationsPanel />
          <TriggersPanel disabled />
        </>
      )}
      {view === 'live' && expId && (
        <>
          <TriggersPanel expId={expId} />
          <EventLogPanel events={events} />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Replace CameraTab in App.tsx**

Find the line `import CameraTab from './pages/CameraTab'` and replace with:

```tsx
import ExperimentRecordingTab from './pages/ExperimentRecordingTab'
```

Find the tab rendering — wherever `<CameraTab ... />` is used, swap to `<ExperimentRecordingTab ... />`. Find the tab label (likely "Camera") and rename to "Experiment Recording".

- [ ] **Step 3: Delete CameraTab.tsx**

```bash
git rm pymice/frontend/src/pages/CameraTab.tsx
```

- [ ] **Step 4: Create stub panels so the build passes**

We reference IntegrationsPanel, TriggersPanel, EventLogPanel — create minimal stubs.

Create `pymice/frontend/src/components/IntegrationsPanel.tsx`:

```tsx
export default function IntegrationsPanel() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <h3 className="font-semibold mb-2">Hardware Integrations</h3>
      <p className="text-sm text-gray-500">(wired in Task 15)</p>
    </div>
  )
}
```

Create `pymice/frontend/src/components/TriggersPanel.tsx`:

```tsx
interface Props { expId?: string; disabled?: boolean }
export default function TriggersPanel(_props: Props) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <h3 className="font-semibold mb-2">Triggers</h3>
      <p className="text-sm text-gray-500">(wired in Task 16)</p>
    </div>
  )
}
```

Create `pymice/frontend/src/components/EventLogPanel.tsx`:

```tsx
import type { ExperimentEvent } from '@/types'

interface Props { events: ExperimentEvent[] }

export default function EventLogPanel({ events }: Props) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <h3 className="font-semibold mb-2">Event Log</h3>
      <div className="text-xs font-mono space-y-1 max-h-64 overflow-auto">
        {events.slice(-100).map((e, i) => (
          <div key={i}>
            <span className="text-gray-500">{e.t?.toFixed(2) ?? '—'}s</span>{' '}
            <span className="text-primary-600">{e.type}</span>{' '}
            <span>{JSON.stringify({ ...e, type: undefined, t: undefined })}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Typecheck + lint**

```bash
cd pymice/frontend
npm run lint
npm run build
```

Both must pass.

- [ ] **Step 6: Commit**

```bash
git add pymice/frontend/src/pages/ExperimentRecordingTab.tsx \
        pymice/frontend/src/App.tsx \
        pymice/frontend/src/components/IntegrationsPanel.tsx \
        pymice/frontend/src/components/TriggersPanel.tsx \
        pymice/frontend/src/components/EventLogPanel.tsx
git rm pymice/frontend/src/pages/CameraTab.tsx
git commit -m "feat(frontend): replace CameraTab with ExperimentRecordingTab + panel stubs"
```

---

## Task 15: Implement IntegrationsPanel UI

**Files:**
- Modify: `pymice/frontend/src/components/IntegrationsPanel.tsx`

- [ ] **Step 1: Implement the panel**

Replace the stub with:

```tsx
import { useEffect, useState } from 'react'
import { experimentApi } from '@/services/api'
import type { Integration, SerialPort } from '@/types'

export default function IntegrationsPanel() {
  const [items, setItems] = useState<Integration[]>([])
  const [showModal, setShowModal] = useState(false)
  const [testResults, setTestResults] = useState<Record<string, 'ok' | 'err' | 'pending' | undefined>>({})

  const reload = () => experimentApi.listIntegrations().then((r) => setItems(r.data.data?.integrations ?? []))
  useEffect(() => { reload() }, [])

  const onTest = async (id: string) => {
    setTestResults((s) => ({ ...s, [id]: 'pending' }))
    const r = await experimentApi.testIntegration(id)
    setTestResults((s) => ({ ...s, [id]: r.data.success ? 'ok' : 'err' }))
  }

  const onDelete = async (id: string) => {
    if (!confirm(`Delete integration ${id}?`)) return
    try {
      await experimentApi.deleteIntegration(id)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail?.error === 'in_use') {
        if (!confirm(`In use by triggers ${detail.triggers.join(', ')}. Force delete?`)) return
        await experimentApi.deleteIntegration(id, true)
      } else {
        alert(`Delete failed: ${JSON.stringify(detail)}`)
        return
      }
    }
    reload()
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Hardware Integrations</h3>
        <button onClick={() => setShowModal(true)} className="text-sm bg-primary-600 text-white px-3 py-1 rounded">
          + Add Integration
        </button>
      </div>
      {items.length === 0 && <p className="text-sm text-gray-500">None configured.</p>}
      <ul className="space-y-2">
        {items.map((i) => (
          <li key={i.id} className="flex items-center gap-3 text-sm">
            <span className={`w-2 h-2 rounded-full ${
              testResults[i.id] === 'ok' ? 'bg-green-500' :
              testResults[i.id] === 'err' ? 'bg-red-500' :
              testResults[i.id] === 'pending' ? 'bg-yellow-500' : 'bg-gray-400'
            }`} />
            <span className="font-medium">{i.name}</span>
            <span className="text-gray-500">
              [{i.kind}{' '}
              {i.kind === 'serial'
                ? (i.config as any).port
                : (i.config as any).base_url}]
            </span>
            <button onClick={() => onTest(i.id)} className="ml-auto text-xs border px-2 py-1 rounded">Test</button>
            <button onClick={() => onDelete(i.id)} className="text-xs text-red-600">Delete</button>
          </li>
        ))}
      </ul>
      {showModal && <AddModal onClose={() => { setShowModal(false); reload() }} />}
    </div>
  )
}

function AddModal({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState<'serial' | 'http'>('serial')
  const [name, setName] = useState('')
  const [ports, setPorts] = useState<SerialPort[]>([])
  const [port, setPort] = useState('')
  const [baud, setBaud] = useState(115200)
  const [baseUrl, setBaseUrl] = useState('http://localhost:9000')
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (kind === 'serial') {
      experimentApi.listSerialPorts().then((r) => {
        const list = r.data.data?.ports ?? []
        setPorts(list)
        if (list.length > 0) setPort(list[0].device)
      })
    }
  }, [kind])

  const submit = async () => {
    setErr(null)
    const id = `i-${Date.now().toString(36)}`
    const integration =
      kind === 'serial'
        ? { id, name, kind, config: { port, baud, newline: '\n' } }
        : { id, name, kind, config: { base_url: baseUrl, default_method: 'POST' as const, default_timeout_sec: 2, headers: {} } }
    try {
      await experimentApi.createIntegration(integration as any)
      onClose()
    } catch (e: any) {
      setErr(e.response?.data?.detail ?? String(e))
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 p-6 rounded-lg w-full max-w-md space-y-3">
        <h4 className="font-semibold">Add Integration</h4>
        <label className="block text-sm">
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value as any)} className="block w-full border rounded px-2 py-1 mt-1">
            <option value="serial">Serial (Arduino / ESP32 USB)</option>
            <option value="http">HTTP (ESP32 WiFi / LAN)</option>
          </select>
        </label>
        <label className="block text-sm">
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1" />
        </label>
        {kind === 'serial' ? (
          <>
            <label className="block text-sm">
              Port
              <select value={port} onChange={(e) => setPort(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1">
                {ports.map((p) => (
                  <option key={p.device} value={p.device}>{p.device} — {p.description}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Baud
              <select value={baud} onChange={(e) => setBaud(Number(e.target.value))} className="block w-full border rounded px-2 py-1 mt-1">
                {[9600, 19200, 57600, 115200, 230400, 921600].map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
          </>
        ) : (
          <label className="block text-sm">
            Base URL
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1" />
            <span className="text-xs text-gray-500">localhost or RFC1918 LAN only</span>
          </label>
        )}
        {err && <p className="text-sm text-red-600">{err}</p>}
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1 border rounded">Cancel</button>
          <button onClick={submit} disabled={!name} className="px-3 py-1 bg-primary-600 text-white rounded disabled:opacity-50">Save</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck + lint**

```bash
cd pymice/frontend
npm run lint
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add pymice/frontend/src/components/IntegrationsPanel.tsx
git commit -m "feat(frontend): IntegrationsPanel — add/list/test/delete hardware bindings"
```

---

## Task 16: Implement TriggersPanel UI

**Files:**
- Modify: `pymice/frontend/src/components/TriggersPanel.tsx`

- [ ] **Step 1: Implement the panel**

Replace the stub:

```tsx
import { useEffect, useState } from 'react'
import { experimentApi } from '@/services/api'
import type { Integration, TriggerRule } from '@/types'

interface Props { expId?: string; disabled?: boolean }

export default function TriggersPanel({ expId, disabled }: Props) {
  const [rules, setRules] = useState<TriggerRule[]>([])
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [showAdd, setShowAdd] = useState(false)

  const reload = async () => {
    if (!expId || disabled) return
    const r = await experimentApi.listTriggers()
    setRules(r.data.data?.triggers ?? [])
  }
  useEffect(() => {
    reload()
    experimentApi.listIntegrations().then((r) => setIntegrations(r.data.data?.integrations ?? []))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expId])

  const onDelete = async (id: string) => {
    if (!confirm(`Delete trigger ${id}?`)) return
    await experimentApi.deleteTrigger(id)
    reload()
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Triggers</h3>
        {!disabled && expId && (
          <button onClick={() => setShowAdd(true)} className="text-sm bg-primary-600 text-white px-3 py-1 rounded">
            + Add Trigger
          </button>
        )}
      </div>
      {disabled && (
        <p className="text-sm text-gray-500">Start an experiment to attach triggers. Configure Integrations first.</p>
      )}
      {!disabled && rules.length === 0 && <p className="text-sm text-gray-500">No triggers.</p>}
      <ul className="space-y-1 text-sm">
        {rules.map((r) => (
          <li key={r.id} className="flex items-center gap-2">
            <span className="font-medium">{r.name}</span>
            <span className="text-gray-500">
              on {r.match.event_type}{r.match.roi_name ? `(${r.match.roi_name})` : ''} →{' '}
              {r.action.kind === 'log' ? `log:${r.action.label}` : `int:${r.action.integration_id}`}
            </span>
            <button onClick={() => onDelete(r.id)} className="ml-auto text-xs text-red-600">Delete</button>
          </li>
        ))}
      </ul>
      {showAdd && expId && (
        <AddTrigger
          integrations={integrations}
          onClose={() => { setShowAdd(false); reload() }}
        />
      )}
    </div>
  )
}

function AddTrigger({ integrations, onClose }: { integrations: Integration[]; onClose: () => void }) {
  const [name, setName] = useState('')
  const [evtType, setEvtType] = useState<'roi_entry' | 'roi_exit' | 'tick' | 'frame_drop'>('roi_entry')
  const [roiName, setRoiName] = useState('')
  const [cooldown, setCooldown] = useState(0)
  const [minDwell, setMinDwell] = useState(0)
  const [actionKind, setActionKind] = useState<'integration' | 'log'>('integration')
  const [integrationId, setIntegrationId] = useState(integrations[0]?.id ?? '')
  const [payload, setPayload] = useState('')
  const [label, setLabel] = useState('')

  const submit = async () => {
    const rule: TriggerRule = {
      id: `t-${Date.now().toString(36)}`,
      name,
      match: {
        event_type: evtType,
        roi_name: roiName || null,
        cooldown_sec: cooldown || null,
        min_dwell_sec: evtType === 'roi_exit' ? (minDwell || null) : null,
      },
      action: actionKind === 'log'
        ? { kind: 'log', label }
        : { kind: 'integration', integration_id: integrationId, payload, timeout_sec: 2 },
    }
    await experimentApi.createTrigger(rule)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 p-6 rounded-lg w-full max-w-md space-y-3">
        <h4 className="font-semibold">Add Trigger</h4>
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="block w-full border rounded px-2 py-1" />
        <label className="block text-sm">
          Event
          <select value={evtType} onChange={(e) => setEvtType(e.target.value as any)} className="block w-full border rounded px-2 py-1 mt-1">
            <option value="roi_entry">roi_entry</option>
            <option value="roi_exit">roi_exit</option>
            <option value="tick">tick</option>
            <option value="frame_drop">frame_drop</option>
          </select>
        </label>
        <input placeholder="ROI name (blank = any)" value={roiName} onChange={(e) => setRoiName(e.target.value)} className="block w-full border rounded px-2 py-1" />
        <label className="block text-sm">
          Cooldown (s)
          <input type="number" min={0} step={0.1} value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))} className="block w-full border rounded px-2 py-1 mt-1" />
        </label>
        {evtType === 'roi_exit' && (
          <label className="block text-sm">
            Min dwell (s)
            <input type="number" min={0} step={0.1} value={minDwell} onChange={(e) => setMinDwell(Number(e.target.value))} className="block w-full border rounded px-2 py-1 mt-1" />
          </label>
        )}
        <label className="block text-sm">
          Action
          <select value={actionKind} onChange={(e) => setActionKind(e.target.value as any)} className="block w-full border rounded px-2 py-1 mt-1">
            <option value="integration">Integration</option>
            <option value="log">Log marker</option>
          </select>
        </label>
        {actionKind === 'integration' ? (
          <>
            <label className="block text-sm">
              Send to
              <select value={integrationId} onChange={(e) => setIntegrationId(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1">
                {integrations.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.kind})</option>)}
              </select>
            </label>
            <input placeholder="Payload (e.g. DROP)" value={payload} onChange={(e) => setPayload(e.target.value)} className="block w-full border rounded px-2 py-1" />
          </>
        ) : (
          <input placeholder="Log label" value={label} onChange={(e) => setLabel(e.target.value)} className="block w-full border rounded px-2 py-1" />
        )}
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1 border rounded">Cancel</button>
          <button onClick={submit} disabled={!name} className="px-3 py-1 bg-primary-600 text-white rounded disabled:opacity-50">Save</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck + lint**

```bash
cd pymice/frontend
npm run lint
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add pymice/frontend/src/components/TriggersPanel.tsx
git commit -m "feat(frontend): TriggersPanel — add/list/delete trigger rules"
```

---

## Task 17: Documentation updates

**Files:**
- Modify: `pymice/CLAUDE.md` (if exists at that path) or repo-root `CLAUDE.md`
- Modify: `docs/diferenciais.md`

- [ ] **Step 1: Update CLAUDE.md API surface**

Locate the project's `CLAUDE.md` (most likely `proj-pymice_web/CLAUDE.md`). Find the `## API surface` section. Add this line after the existing routers list:

```markdown
- `/api/experiment` — live tracking (start/stop/status), Arduino/ESP32 integrations CRUD, trigger rules, WebSocket `/events`, artifact download.
```

In `## Domain notes`, append:

```markdown
- **Experiment Recording (live):** `app/processing/live_experiment.py` owns a daemon-thread loop that consumes `camera_state["stream"]`, runs YOLO per frame, writes raw video + tracking JSONL + events JSONL into `temp/experiments/<exp_id>/`, and emits events to `EventBus`. The router (`app/routers/experiment.py`) exposes lifecycle endpoints and the WebSocket. Hardware bindings (Arduino serial, ESP32 HTTP) live in `app/services/integrations.py` and persist in `temp/integrations.json`. **Singleton:** one experiment per process — `POST /start` is 409 if another is running. **Annotated display:** the loop writes the annotated frame into `camera_state["annotated_frame"]`; `/api/camera/frame` prefers it when present, so the existing frontend polling shows overlays without a new endpoint.
```

- [ ] **Step 2: Update docs/diferenciais.md**

In `docs/diferenciais.md`, find the section listing differentials (item 7 — Stack web) and add a new differential after it:

```markdown
### 8. Tracking ao vivo, gravação e closed-loop em uma única aba
A aba **Experiment Recording** (`pages/ExperimentRecordingTab.tsx`) consome a câmera USB diretamente, desenha ROIs sobre o frame ao vivo (componente compartilhado `ROICanvas`), roda YOLO frame-a-frame e grava simultaneamente o **vídeo bruto** e um **`tracking.jsonl`** sincronizado por `frame_idx`. Eventos de ROI (`roi_entry`, `roi_exit`) e disparos são publicados em um **canal WebSocket** (`/api/experiment/events`); regras de **trigger** declarativas (cooldown, min_dwell) podem disparar **ações em hardware** — Arduino/ESP32 via USB serial, ou ESP32 via HTTP em LAN. Tudo em um único processo FastAPI, com a porta serial mantida aberta entre disparos para evitar reset-on-open do Arduino.
```

- [ ] **Step 3: Commit**

```bash
git add proj-pymice_web/CLAUDE.md docs/diferenciais.md
# Note: path depends on which CLAUDE.md you edited. Adjust accordingly.
git commit -m "docs: cover Experiment Recording (CLAUDE.md API surface + Domain notes; diferenciais)"
```

---

## Task 18: Manual integration check

**No file changes.** Execute the 12-step manual check from the spec.

- [ ] **Step 1: Start backend + frontend**

```bash
source uv-env/bin/activate
./pymice/run.sh start
```

Open `http://localhost:5765`.

- [ ] **Step 2: Smoke test — golden path**

Navigate to **Experiment Recording**:

1. Select camera 0, click **Start Stream** → frame visible.
2. (Optional, no hardware) Open Integrations → Add HTTP integration `http://localhost:9000` named "Mock". Open a listener in another terminal: `nc -lk 9000`. Click **Test** → indicator goes green; `nc` shows incoming request.
3. Pick the Rectangle tool, draw an ROI on the left half of the frame.
4. Pick the Circle tool, draw an ROI on the right side.
5. Pick a YOLO model (e.g. `yolov8n.pt` if present in `temp/models/`).
6. Click **Start Experiment**. Verify state transitions to Live; annotated bbox/circle appear over the canvas as YOLO detects a moving object.
7. Move a tracked object across both ROIs. Event Log shows `roi_entry`/`roi_exit` for each crossing.
8. Open Triggers → Add a trigger: `roi_entry`, ROI 1, action = HTTP integration with payload "DROP". Move the object into ROI 1 → `nc` receives `DROP`.
9. Repeat the entry within `cooldown_sec` → second event appears in log with `result.skipped == "cooldown"`.
10. Click **Stop Experiment**. Done view shows 4 downloadable artifacts.
11. Inspect `temp/experiments/exp_*/`:
    - `raw.mp4` plays in any video player.
    - `tracking.jsonl` has one JSON per frame; `head -2 tracking.jsonl` and confirm `frame_idx`, `centroid_x/y`, `active_roi` fields.
    - `events.jsonl` has `started`/`roi_*`/`trigger`/`stopped` lines.
    - `metadata.json` shows `state: "stopped"`.

- [ ] **Step 3: Failure case — stream lost**

1. Click **New Experiment**, redraw ROIs, **Start Experiment** again.
2. Unplug the USB camera. Within ~2 seconds, UI transitions to Done with `reason: stream_lost` in the last `stopped` event.
3. Partial artifacts exist in `temp/experiments/exp_*/`.

- [ ] **Step 4: pytest sweep + typecheck**

```bash
cd pymice/backend
pytest tests/ -v

cd ../frontend
npm run lint
npm run build
```

All must pass.

- [ ] **Step 5: Stop services**

```bash
cd ../..
./pymice/run.sh stop
```

- [ ] **Step 6: Commit final manual-check note (optional)**

If you discovered anything during the check that requires a small fix, make it and commit it scoped — don't bundle with this task.

---

## Acceptance summary

You are done when:

- All 5 pytest files pass (`test_event_bus`, `test_trigger_evaluator`, `test_integration_serial`, `test_integration_http`, `test_live_experiment_loop`).
- `npm run build` typechecks; `npm run lint` produces zero warnings.
- The 12-step manual check passes.
- `git status` is clean.
- The 18 commits land on a feature branch, one per task; PR description references the spec at `docs/superpowers/specs/2026-05-15-experiment-recording-design.md`.

---

## Self-review notes (post-write, applied inline)

Items found during the review pass and fixed in place:
- **Schema gap:** `TriggerAction` originally accepted `kind: "webhook"` but the backend dispatcher in Task 10 only branches on `"integration"` / `"log"`. Schemas now use `"integration"` consistently (webhook is just `kind: integration` against an `http` integration).
- **`pytest-asyncio`:** added to install step in Task 3 since the tests use `@pytest.mark.asyncio`.
- **Vite WS proxy:** the WS subscriber needs `ws: true` in `vite.config.ts` to round-trip through the dev server; called out in Task 12 step 3.
- **`_main_loop_ref` thread-safety:** capturing the loop in `@router.on_event("startup")` ensures the loop is set before any experiment can start. Spelled out in Task 10.
- **Frame index source of truth:** the loop increments `_frames_processed` after writing the JSONL line so `frame_idx` matches the index used in events emitted before the increment. This is consistent across all tasks.
