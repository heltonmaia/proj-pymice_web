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
    create_integration(
        Integration(
            id="i-2",
            name="lan",
            kind="http",
            config=IntegrationConfigHttp(base_url="http://192.168.1.42"),
        ),
        registry_path=None,
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
