"""Playwright configuration for E2E tests."""

import os
import pytest


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Launch Chromium headless."""
    return {"headless": True, "args": ["--no-sandbox"]}
