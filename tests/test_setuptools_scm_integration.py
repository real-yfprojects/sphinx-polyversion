"""
Integration test to verify PipWithSetuptoolsScm environment variable behavior.

This test verifies that our solution correctly sets environment variables without needing network access.
"""

import os
import tempfile
from pathlib import Path

import pytest

from sphinx_polyversion.pyvenv import PipWithSetuptoolsScm


@pytest.mark.asyncio
async def test_pip_with_setuptools_scm_env_vars():
    """Test that PipWithSetuptoolsScm correctly sets environment variables in the runtime environment."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create a test project directory
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        
        # Create pyproject.toml (doesn't need to be complete since we're not installing)
        (project_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        
        # Create virtual environment path
        venv_path = tmp_path / "venv"
        
        # Test that environment variables are correctly set in the environment
        env_instance = PipWithSetuptoolsScm(
            path=project_path,
            name="v1.2.3",
            venv=venv_path,
            args=["--no-deps"],
            package_name="mypackage"
        )
        
        # Check that the environment variables are set correctly
        assert "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE" in env_instance.env
        assert env_instance.env["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE"] == "1.2.3"
        
        # Test that the environment is applied when activating the environment
        test_env = {"EXISTING_VAR": "existing_value"}
        activated_env = env_instance.apply_overrides(test_env.copy())
        
        # Should contain both existing and new environment variables
        assert "EXISTING_VAR" in activated_env
        assert activated_env["EXISTING_VAR"] == "existing_value"
        assert "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE" in activated_env
        assert activated_env["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE"] == "1.2.3"


def test_setuptools_scm_solution_demo():
    """
    Demonstrate that the setuptools-scm solution works by showing the environment variable behavior.
    
    This is a simple unit test that shows our solution addresses the core issue without needing network access.
    """
    # Simulate the problem: setuptools-scm fails when there's no .git directory
    # Our solution: set SETUPTOOLS_SCM_PRETEND_VERSION environment variable
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        venv_path = tmp_path / "venv"
        
        # Create environment with version-like ref name
        env = PipWithSetuptoolsScm(
            path=project_path,
            name="v2.1.0-alpha1",  # Complex version string
            venv=venv_path,
            args=["--no-deps"],
        )
        
        # Verify that setuptools-scm environment variable is set
        assert "SETUPTOOLS_SCM_PRETEND_VERSION" in env.env
        assert env.env["SETUPTOOLS_SCM_PRETEND_VERSION"] == "2.1.0-alpha1"
        
        # Verify that non-version refs don't create environment variables
        env_main = PipWithSetuptoolsScm(
            path=project_path,
            name="main",  # Non-version ref
            venv=venv_path,
            args=["--no-deps"],
        )
        
        # Should not have setuptools-scm environment variables
        scm_vars = [k for k in env_main.env.keys() if k.startswith("SETUPTOOLS_SCM_")]
        assert len(scm_vars) == 0


if __name__ == "__main__":
    # Can be run directly for manual testing
    import asyncio
    asyncio.run(test_pip_with_setuptools_scm_env_vars())
    test_setuptools_scm_solution_demo()
    print("All tests passed!")