"""Integration tests for the `setuptools_scm` module."""

import asyncio
import contextlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

with contextlib.suppress(ImportError):
    from sphinx_polyversion.setuptools_scm import version_for_ref

from tests.test_git import NO_FS_MONITOR, no_git_env

if shutil.which("git") is None:
    pytest.skip("git is required for these integration tests", allow_module_level=True)
pytest.importorskip("setuptools_scm")
pytest.importorskip("packaging")


async def _run_git(args, cwd):
    git = ("git", *NO_FS_MONITOR)
    env = no_git_env()
    p = await asyncio.create_subprocess_exec(*git, *args, cwd=cwd, env=env)
    r = await p.wait()
    assert r == 0, f"git {' '.join(args)} failed with exit code {r}"


@pytest_asyncio.fixture
async def temp_git_repo(tmp_path: Path) -> Path:
    """Create dummy git repo using `setuptools_scm`."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Write minimal pyproject.toml for setuptools_scm
    (repo / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools>=61", "setuptools-scm"]
build-backend = "setuptools.build_meta"

[project]
name = "My-Dist_Name"

[tool.setuptools_scm]
""",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Test Project\n", encoding="utf-8")

    # Initialize git repo and create a tag
    await _run_git(["init"], cwd=repo)
    await _run_git(["config", "user.email", "example@example.com"], cwd=repo)
    await _run_git(["config", "user.name", "example"], cwd=repo)
    await _run_git(["config", "commit.gpgsign", "false"], cwd=repo)
    await _run_git(["config", "init.defaultBranch", "main"], cwd=repo)
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "initial"], cwd=repo)
    await _run_git(["tag", "v1.2.3"], cwd=repo)

    return repo


@pytest.mark.asyncio
async def test_version_for_ref_determines_dist_name_and_version(temp_git_repo: Path):
    """Test that `version_for_ref` determines version and dist name correctly."""
    result = await version_for_ref(temp_git_repo, "HEAD")
    assert result is not None, "Expected a version from setuptools-scm"
    version, dist_name = result
    # Distribution name should be canonicalized
    assert dist_name == "my-dist-name"
    # On exact tag, setuptools-scm should return the tag version
    assert version == "1.2.3"


@pytest.mark.asyncio
async def test_driver_sets_env_variable_from_setuptools_scm(
    temp_git_repo: Path, monkeypatch
):
    """Test that the driver sets the correct env variable from setuptools-scm."""
    import sphinx_polyversion.setuptools_scm as scm_mod

    # Patch DefaultDriver.init_environment to return a fake env holder
    async def fake_init_environment(self, path, rev):
        return SimpleNamespace(env={})

    monkeypatch.setattr(
        scm_mod.DefaultDriver, "init_environment", fake_init_environment
    )

    # Create driver instance without calling __init__
    driver = object.__new__(scm_mod.SetuptoolsScmDriver)
    driver.root = temp_git_repo

    # Fake GitRef-like object expected by the driver
    rev = SimpleNamespace(name="HEAD", obj="HEAD")

    env_holder = await driver.init_environment(temp_git_repo, rev)
    # dist name from the repo is "my-dist-name" -> var name uses "-" -> "_" uppercased
    expected_key = "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MY_DIST_NAME"
    assert expected_key in env_holder.env
    assert env_holder.env[expected_key] == "1.2.3"
