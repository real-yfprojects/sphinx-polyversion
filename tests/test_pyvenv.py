"""Test the python environments in the `pyvenv` module."""

import asyncio
from pathlib import Path

import pytest

from sphinx_polyversion.pyvenv import (
    Pip,
    Poetry,
    VenvWrapper,
    VirtualenvWrapper,
    VirtualPythonEnvironment,
)


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


class TestVirtualPythonEnvionment:
    """Test the `VirtualPythonEnvironment` class."""

    @pytest.mark.asyncio()
    async def test_creation_with_venv(self, tmp_path: Path):
        """Test the `create_venv` method with a `VenvWrapper`."""
        location = tmp_path / "venv"
        env = VirtualPythonEnvironment(
            tmp_path, "main", location, creator=VenvWrapper()
        )

        await env.create_venv()
        assert (location / "bin" / "python").exists()

    @pytest.mark.asyncio()
    async def test_creation_without_creator(self, tmp_path: Path):
        """Test the `create_venv` method without any creator."""
        location = tmp_path / "venv"
        env = VirtualPythonEnvironment(tmp_path, "main", location)

        await env.create_venv()
        assert not (location / "bin" / "python").exists()

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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


class TestPip:
    """Test the `Pip` class."""

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
    async def test_creation_without_creator(self, tmp_path: Path):
        """Test the `create_venv` method without any creator."""
        location = tmp_path / "venv"
        env = Pip(tmp_path, "main", location, args=["tomli"], temporary=False)

        await env.create_venv()
        assert not (location / "bin" / "python").exists()

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
    async def test_creation_without_creator_temporary(self, tmp_path: Path):
        """Test the `create_venv` method without any creator."""
        location = "tmpvenv"
        with pytest.raises(
            ValueError,
            match="Cannot create temporary virtual environment when creator is None",
        ):
            Pip(tmp_path, "main", location, args=["tomli"], temporary=True)

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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


class TestPoetry:
    """Test the `Poetry` environment."""

    @pytest.mark.asyncio()
    async def test_simple_project(self, tmp_path: Path):
        """Test installing a simple project with poetry."""
        # create source files
        src_location = tmp_path / "src"
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

            # test that tomli is installed
            out, err, rc = await env.run(
                "python",
                "-c",
                "import tomli",
                stdout=asyncio.subprocess.PIPE,
            )
            assert rc == 0

    @pytest.mark.asyncio()
    async def test_simple_project_with_optional_deps(self, tmp_path: Path):
        """Test installing a simple project with poetry."""
        # create source files
        src_location = tmp_path / "src"
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

    @pytest.mark.asyncio()
    async def test_create_two_concurrently(self, tmp_path: Path):
        """Test creating two environments concurrently."""
        # create source files
        src_location = tmp_path / "src"
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
