"""Pytest configuration and shared fixtures."""

import logging

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Configure logging for tests."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@pytest.fixture
def tmp_csv(tmp_path):
    """Provide path to temporary CSV file."""
    return tmp_path / "test.csv"
