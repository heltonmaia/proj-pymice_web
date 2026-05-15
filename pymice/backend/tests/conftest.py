"""Shared pytest fixtures for backend tests."""

import asyncio
import pytest


@pytest.fixture
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()
