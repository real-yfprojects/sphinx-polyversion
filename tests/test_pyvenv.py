"""Test the python environments in the `pyvenv` module."""

import asyncio
from pathlib import Path

import pytest

from sphinx_polyversion.pyvenv import (
    Pip,
    PipWithSetuptoolsScm,
    Poetry,
    VenvWrapper,
    VirtualenvWrapper,
    VirtualPythonEnvironment,
)


@pytest.mark.asyncio
async def test_venv_creation(tmp_path: Path):
    """Test the creation of a python virtual environment."""
    location = tmp_path / "venv"
    await VenvWrapper()(location)
    assert location.exists()
    assert (location / "bin" / "python").exists()


@pytest.mark.asyncio
async def test_virtualvenv_creation(tmp_path: Path):
    """Test the creation of a python virtual environment."""
    pytest.importorskip("virtualenv")

    location = tmp_path / "venv"
    await VirtualenvWrapper([])(location)
    assert location.exists()
    assert (location / "bin" / "python").exists()


class TestVirtualPythonEnvionment:
    """Test the `VirtualPythonEnvironment` class."""

    @pytest.mark.asyncio
    async def test_creation_with_venv(self, tmp_path: Path):
        """Test the `create_venv` method with a `VenvWrapper`."""
        location = tmp_path / "venv"
        env = VirtualPythonEnvironment(
            tmp_path, "main", location, creator=VenvWrapper()
        )

        await env.create_venv()
        assert (location / "bin" / "python").exists()

    @pytest.mark.asyncio
    async def test_creation_without_creator(self, tmp_path: Path):
        """Test the `create_venv` method without any creator."""
        location = tmp_path / "venv"
        env = VirtualPythonEnvironment(tmp_path, "main", location)

        await env.create_venv()
        assert not (location / "bin" / "python").exists()

    @pytest.mark.asyncio
    async def test_run_without_creator_no_existing(self, tmp_path: Path):
        """Test running a command without an existing venv and without creator."""
        location = tmp_path / "novenv"

        async with VirtualPythonEnvironment(tmp_path, "main", location) as env:
            with pytest.raises(FileNotFoundError, match="There is no virtual"):
                out, err, rc = await env.run(
                    "python",
                    "-c",
                    "import sys; print(sys.prefix)",
                    stdout=asyncio.subprocess.PIPE,
                )

    @pytest.mark.asyncio
    async def test_run_without_creator(self, tmp_path: Path):
        """Test running a command in an existing venv."""
        location = tmp_path / "venv"

        # create env
        await VenvWrapper([])(location)

        async with VirtualPythonEnvironment(tmp_path, "main", location) as env:
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(location) == out.strip()

    @pytest.mark.asyncio
    async def test_run_with_creator(self, tmp_path: Path):
        """Test running a command in a new venv."""
        location = tmp_path / "venv"

        async with VirtualPythonEnvironment(
            tmp_path, "main", location, creator=VenvWrapper()
        ) as env:
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(location) == out.strip()

    @pytest.mark.asyncio
    async def test_run_with_env_variables(self, tmp_path: Path):
        """Test passing an environment variable to a venv."""
        location = tmp_path / "venv"

        async with VirtualPythonEnvironment(
            tmp_path, "main", location, creator=VenvWrapper(), env={"TESTVAR": "1"}
        ) as env:
            out, err, rc = await env.run(
                "python",
                "-c",
                "import os; print(os.environ['TESTVAR'])",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert out.strip() == "1"


class TestPip:
    """Test the `Pip` class."""

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_creation_with_venv(self, tmp_path: Path):
        """Test the `create_venv` method with a `VenvWrapper`."""
        location = tmp_path / "venv"
        env = Pip(
            tmp_path,
            "main",
            location,
            args=["tomli"],
            creator=VenvWrapper(),
            temporary=False,
        )

        await env.create_venv()
        assert (location / "bin" / "python").exists()

    @pytest.mark.asyncio
    async def test_creation_without_creator(self, tmp_path: Path):
        """Test the `create_venv` method without any creator."""
        location = tmp_path / "venv"
        env = Pip(tmp_path, "main", location, args=["tomli"], temporary=False)

        await env.create_venv()
        assert not (location / "bin" / "python").exists()

    @pytest.mark.asyncio
    async def test_run_without_creator(self, tmp_path: Path):
        """Test running a command in an existing venv."""
        location = tmp_path / "venv"

        # create env
        await VenvWrapper([])(location)

        async with Pip(
            tmp_path, "main", location, args=["tomli"], temporary=False
        ) as env:
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(location) == out.strip()

    @pytest.mark.asyncio
    async def test_run_with_creator(self, tmp_path: Path):
        """Test running a command in a new venv."""
        location = tmp_path / "venv"

        async with Pip(
            tmp_path,
            "main",
            location,
            args=["tomli"],
            creator=VenvWrapper(),
            temporary=False,
        ) as env:
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(location) == out.strip()

    @pytest.mark.asyncio
    async def test_creation_with_venv_temporary(self, tmp_path: Path):
        """Test the `create_venv` method with a `VenvWrapper`."""
        location = "tmpvenv"
        env = Pip(
            tmp_path,
            "main",
            location,
            args=["tomli"],
            creator=VenvWrapper(),
            temporary=True,
        )

        await env.create_venv()
        assert (tmp_path / location / "bin" / "python").exists()

    @pytest.mark.asyncio
    async def test_creation_without_creator_temporary(self, tmp_path: Path):
        """Test the `create_venv` method without any creator."""
        location = "tmpvenv"
        with pytest.raises(
            ValueError,
            match="Cannot create temporary virtual environment when creator is None",
        ):
            Pip(tmp_path, "main", location, args=["tomli"], temporary=True)

    @pytest.mark.asyncio
    async def test_run_with_creator_temporary(self, tmp_path: Path):
        """Test running a command in a new venv."""
        location = "tmpvenv"

        async with Pip(
            tmp_path,
            "main",
            location,
            args=["tomli"],
            creator=VenvWrapper(),
            temporary=True,
        ) as env:
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(tmp_path / location) == out.strip()

    @pytest.mark.asyncio
    async def test_install_into_existing_venv(self, tmp_path: Path):
        """Test installing a package into an existing venv."""
        location = tmp_path / "venv"

        # create env
        await VenvWrapper(with_pip=True)(location)

        # test that tomli is not installed
        proc = await asyncio.create_subprocess_exec(
            str(location / "bin/python"),
            "-c",
            "import tomli",
            stdout=asyncio.subprocess.PIPE,
        )
        rc = await proc.wait()
        assert rc == 1

        # init env with tomli
        async with Pip(tmp_path, "main", location, args=["tomli"]) as env:
            # test that tomli is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import tomli",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

    @pytest.mark.asyncio
    async def test_run_with_env_variables(self, tmp_path: Path):
        """Test passing an environment variable to a venv."""
        location = tmp_path / "venv"

        # create env
        await VenvWrapper(with_pip=True)(location)

        # test that tomli is not installed
        proc = await asyncio.create_subprocess_exec(
            str(location / "bin/python"),
            "-c",
            "import tomli",
            stdout=asyncio.subprocess.PIPE,
        )
        rc = await proc.wait()
        assert rc == 1

        # init env with tomli
        async with Pip(
            tmp_path, "main", location, args=["tomli"], env={"TESTVAR": "1"}
        ) as env:
            # test that tomli is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import os; print(os.environ['TESTVAR'])",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert out.strip() == "1"


class TestPoetry:
    """Test the `Poetry` environment."""

    @pytest.mark.asyncio
    async def test_simple_project(self, tmp_path: Path):
        """Test installing a simple project with poetry."""
        # create source files
        src_location = tmp_path / "test"
        src_location.mkdir()
        src_location.joinpath("__init__.py").touch()

        # create config
        config_location = tmp_path / "pyproject.toml"
        config_location.write_text(
            """
            [tool.poetry]
            name = "test"
            version = "0.1.0"
            description = ""
            authors = ["Author <author@example.com>"]
            license = "MIT"

            [tool.poetry.dependencies]
            python = "^3.8"
            tomli = "*"
            """
        )

        # create poetry env
        async with Poetry(tmp_path, "main", args=[], env={"TESTVAR": "1"}) as env:
            # check sourcing works
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(tmp_path) in out.strip()

            # test that project is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import test",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

            # test that tomli is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import tomli",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

            # test that custom environment variables are passed correctly
            out, err, rc = await env.run(
                "python",
                "-c",
                "import os; print(os.environ['TESTVAR'])",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert out.strip() == "1"

    @pytest.mark.asyncio
    async def test_simple_project_with_optional_deps(self, tmp_path: Path):
        """Test installing a simple project with poetry."""
        # create source files
        src_location = tmp_path / "test"
        src_location.mkdir()
        src_location.joinpath("__init__.py").touch()

        # create config
        config_location = tmp_path / "pyproject.toml"
        config_location.write_text(
            """
            [tool.poetry]
            name = "test"
            version = "0.1.0"
            description = ""
            authors = ["Author <author@example.com>"]
            license = "MIT"

            [tool.poetry.dependencies]
            python = "^3.8"

            [tool.poetry.group.dev]
            optional = true

            [tool.poetry.group.dev.dependencies]
            tomli = "*"
            """
        )

        # create poetry env
        async with Poetry(tmp_path, "main", args=[]) as env:
            # check sourcing works
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(tmp_path) in out.strip()

            # test that project is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import test",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

            # test that tomli is not installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import tomli",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 1

        # create poetry env
        async with Poetry(tmp_path, "main", args=["--with=dev"]) as env:
            # check sourcing works
            out, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0
            assert str(tmp_path) in out.strip()

            # test that project is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import test",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

            # test that tomli is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import tomli",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

    @pytest.mark.asyncio
    async def test_create_two_concurrently(self, tmp_path: Path):
        """Test creating two environments concurrently."""
        # create source files
        src_location = tmp_path / "test"
        src_location.mkdir()
        src_location.joinpath("__init__.py").touch()

        # create config
        config_location = tmp_path / "pyproject.toml"
        config_location.write_text(
            """
            [tool.poetry]
            name = "test"
            version = "0.1.0"
            description = ""
            authors = ["Author <author@example.com>"]
            license = "MIT"

            [tool.poetry.dependencies]
            python = "^3.8"

            [tool.poetry.group.dev]
            optional = true

            [tool.poetry.group.dev.dependencies]
            tomli = "*"
            """
        )

        # create poetry env
        async with Poetry(tmp_path, "main", args=[]) as env:
            # check sourcing works
            first_path, err, rc = await env.run(
                "python",
                "-c",
                "import sys; print(sys.prefix)",
                stdout=asyncio.subprocess.PIPE,
            )
            first_path = first_path.strip()
            assert rc == 0
            assert str(tmp_path) in first_path

            # test that project is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import test",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

            # test that tomli is not installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import tomli",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 1

            # create second poetry env
            async with Poetry(tmp_path, "main", args=["--with=dev"]) as env2:
                # check sourcing works
                out, err, rc = await env2.run(
                    "python",
                    "-c",
                    "import sys; print(sys.prefix)",
                    stdout=asyncio.subprocess.PIPE,
                )
                assert rc == 0
                assert str(tmp_path) in out.strip()
                assert out.strip() != first_path

                # check that old env still works
                out, err, rc = await env.run(
                    "python",
                    "-c",
                    "import sys; print(sys.prefix)",
                    stdout=asyncio.subprocess.PIPE,
                )
                assert rc == 0
                assert first_path == out.strip()

                # test that project is installed
                out, err, rc = await env2.run(
                    "python",
                    "-c",
                    "import test",
                    stdout=asyncio.subprocess.PIPE,
                )
                assert rc == 0

                # test that tomli is installed
                out, err, rc = await env2.run(
                    "python",
                    "-c",
                    "import tomli",
                    stdout=asyncio.subprocess.PIPE,
                )
                assert rc == 0


class TestPipWithSetuptoolsScm:
    """Test the `PipWithSetuptoolsScm` environment."""

    def test_env_variables_created_for_version_ref(self, tmp_path: Path):
        """Test that setuptools-scm environment variables are created for version refs."""
        # Test with version tag
        env = PipWithSetuptoolsScm(
            tmp_path, "v1.2.3", "venv", args=["--no-deps"]
        )
        assert "SETUPTOOLS_SCM_PRETEND_VERSION" in env.env
        assert env.env["SETUPTOOLS_SCM_PRETEND_VERSION"] == "1.2.3"

    def test_env_variables_with_package_name(self, tmp_path: Path):
        """Test that package-specific environment variables are created."""
        env = PipWithSetuptoolsScm(
            tmp_path, "v1.2.3", "venv", args=["--no-deps"], package_name="mypackage"
        )
        assert "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE" in env.env
        assert env.env["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE"] == "1.2.3"

    def test_no_env_variables_for_non_version_ref(self, tmp_path: Path):
        """Test that no environment variables are created for non-version refs."""
        env = PipWithSetuptoolsScm(
            tmp_path, "main", "venv", args=["--no-deps"]
        )
        # Should only have user-provided env vars, no setuptools-scm vars
        scm_vars = [k for k in env.env.keys() if k.startswith("SETUPTOOLS_SCM_")]
        assert len(scm_vars) == 0

    def test_env_variables_merged_with_user_env(self, tmp_path: Path):
        """Test that setuptools-scm env vars are merged with user-provided env vars."""
        user_env = {"USER_VAR": "user_value", "PATH": "/custom/path"}
        env = PipWithSetuptoolsScm(
            tmp_path, "v1.2.3", "venv", args=["--no-deps"], env=user_env
        )
        
        # Should contain both user vars and setuptools-scm vars
        assert "USER_VAR" in env.env
        assert env.env["USER_VAR"] == "user_value"
        assert "PATH" in env.env
        assert env.env["PATH"] == "/custom/path"
        assert "SETUPTOOLS_SCM_PRETEND_VERSION" in env.env
        assert env.env["SETUPTOOLS_SCM_PRETEND_VERSION"] == "1.2.3"

    def test_complex_version_extraction(self, tmp_path: Path):
        """Test that complex version strings are handled correctly."""
        env = PipWithSetuptoolsScm(
            tmp_path, "release-2.1.0-alpha1", "venv", args=["--no-deps"]
        )
        assert "SETUPTOOLS_SCM_PRETEND_VERSION" in env.env
        assert env.env["SETUPTOOLS_SCM_PRETEND_VERSION"] == "2.1.0-alpha1"

    def test_package_name_normalization(self, tmp_path: Path):
        """Test that package names are properly normalized."""
        env = PipWithSetuptoolsScm(
            tmp_path, "v1.2.3", "venv", args=["--no-deps"], package_name="my-package.name"
        )
        assert "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MY_PACKAGE_NAME" in env.env
        assert env.env["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MY_PACKAGE_NAME"] == "1.2.3"
