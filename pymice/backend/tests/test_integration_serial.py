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
