"""Device-selection helpers shared across routers and processing.

Centralises the "is the GPU actually usable?" question so every code path
(video tracking, test-detection, live experiments) degrades to CPU consistently
on hardware whose CUDA arch isn't supported by the installed PyTorch binary —
e.g. an RTX 5060 Ti (sm_120) against a torch built for sm<=90, where
``torch.cuda.is_available()`` returns True but any real kernel raises
"no kernel image is available for execution on the device".
"""
from __future__ import annotations

import torch

_cuda_usable: bool | None = None


def cuda_is_usable() -> bool:
    """True only if CUDA is present AND can actually execute kernels on this GPU.

    ``torch.cuda.is_available()`` only checks that the runtime sees a device; it
    returns True even when the GPU's compute capability isn't in the installed
    PyTorch binary's arch list. Result cached for the process.
    """
    global _cuda_usable
    if _cuda_usable is None:
        _cuda_usable = _probe_cuda()
    return _cuda_usable


def _probe_cuda() -> bool:
    if not torch.cuda.is_available():
        return False
    try:
        major, minor = torch.cuda.get_device_capability()
        if f"sm_{major}{minor}" in torch.cuda.get_arch_list():
            # Exact arch compiled in — usable without launching a kernel.
            return True
    except Exception:
        return False
    # Arch not directly compiled; forward-compatible PTX JIT *might* still work,
    # so confirm with a real op rather than assuming. (This op only runs on
    # already-suspect GPUs, never on ones whose arch is in the list.)
    try:
        probe = torch.zeros(8, device="cuda")
        _ = (probe + 1).sum().item()
        return True
    except Exception:
        return False


def select_device() -> str:
    """Best *actually usable* device string: 'cuda', 'mps', or 'cpu'."""
    if cuda_is_usable():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def disable_cuda_if_unsupported() -> bool:
    """Hide an unusable GPU from the whole process.

    If a GPU is present but its arch isn't usable by this torch build, override
    ``torch.cuda.is_available`` to return False so all downstream code — including
    third-party *hardcoded* ``torch.cuda.is_available()`` checks inside SAM3 and
    Ultralytics — falls back to CPU instead of crashing mid-run. Returns True if
    it disabled CUDA; no-op (returns False) when the GPU is usable or absent.
    """
    if torch.cuda.is_available() and not cuda_is_usable():
        torch.cuda.is_available = lambda: False
        return True
    return False
