"""Test the python environments in the `pyvenv` module."""

from pathlib import Path

import pytest

from sphinx_polyversion.pyvenv import VenvWrapper, VirtualenvWrapper


@pytest.mark.asyncio()
async def test_venv_creation(tmp_path: Path):
    """Test the creation of a python virtual environment."""
    location = tmp_path / "venv"
    await VenvWrapper()(location)
    assert location.exists()
    assert (location / "bin" / "python").exists()


@pytest.mark.asyncio()
async def test_virtualvenv_creation(tmp_path: Path):
    """Test the creation of a python virtual environment."""
    pytest.importorskip("virtualenv")

    location = tmp_path / "venv"
    await VirtualenvWrapper([])(location)
    assert location.exists()
    assert (location / "bin" / "python").exists()
