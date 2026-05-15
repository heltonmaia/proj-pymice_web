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
                self._port = None
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
