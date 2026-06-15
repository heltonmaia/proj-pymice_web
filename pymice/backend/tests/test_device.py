"""Tests for app.utils.device — the GPU-arch usability probe / CPU fallback."""
import pytest

from app.utils import device as dev


@pytest.fixture(autouse=True)
def _reset_probe_cache():
    """The usability result is memoized in a module global; reset around each test."""
    dev._cuda_usable = None
    yield
    dev._cuda_usable = None


def _raise_no_kernel(*args, **kwargs):
    raise RuntimeError("CUDA error: no kernel image is available for execution on the device")


def test_unusable_when_cuda_absent(monkeypatch):
    monkeypatch.setattr(dev.torch.cuda, "is_available", lambda: False)
    assert dev.cuda_is_usable() is False
    assert dev.select_device() == "cpu"


def test_usable_when_arch_in_list_without_launching_kernel(monkeypatch):
    monkeypatch.setattr(dev.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(dev.torch.cuda, "get_device_capability", lambda *a: (8, 6))
    monkeypatch.setattr(dev.torch.cuda, "get_arch_list", lambda: ["sm_80", "sm_86", "sm_90"])
    # If the arch is in the list we must NOT launch a probe kernel.
    monkeypatch.setattr(dev.torch, "zeros", _raise_no_kernel)
    assert dev.cuda_is_usable() is True
    assert dev.select_device() == "cuda"


def test_unusable_when_arch_absent_and_kernel_fails(monkeypatch):
    monkeypatch.setattr(dev.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(dev.torch.cuda, "get_device_capability", lambda *a: (12, 0))
    monkeypatch.setattr(dev.torch.cuda, "get_arch_list", lambda: ["sm_80", "sm_86", "sm_90"])
    monkeypatch.setattr(dev.torch, "zeros", _raise_no_kernel)
    assert dev.cuda_is_usable() is False
    assert dev.select_device() == "cpu"


def test_disable_cuda_if_unsupported_hides_unusable_gpu(monkeypatch):
    monkeypatch.setattr(dev.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(dev.torch.cuda, "get_device_capability", lambda *a: (12, 0))
    monkeypatch.setattr(dev.torch.cuda, "get_arch_list", lambda: ["sm_90"])
    monkeypatch.setattr(dev.torch, "zeros", _raise_no_kernel)
    assert dev.disable_cuda_if_unsupported() is True
    assert dev.torch.cuda.is_available() is False  # patched process-wide


def test_disable_is_noop_when_gpu_usable(monkeypatch):
    monkeypatch.setattr(dev.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(dev.torch.cuda, "get_device_capability", lambda *a: (8, 6))
    monkeypatch.setattr(dev.torch.cuda, "get_arch_list", lambda: ["sm_86"])
    assert dev.disable_cuda_if_unsupported() is False
    assert dev.torch.cuda.is_available() is True  # left alone
