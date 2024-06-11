"""Subclasses of :class:`Environment` supporting python virtual environments."""

from __future__ import annotations

import asyncio
import os
from asyncio.subprocess import PIPE
from inspect import isawaitable
from logging import getLogger
from pathlib import Path
from subprocess import CalledProcessError
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Sequence,
    Tuple,
    cast,
)
from venv import EnvBuilder

from sphinx_polyversion.builder import BuildError
from sphinx_polyversion.environment import Environment
from sphinx_polyversion.utils import to_thread

if TYPE_CHECKING:
    from typing_extensions import Self

logger = getLogger(__name__)


class VenvWrapper(EnvBuilder):
    """Build your virtual environments using the build-in venv module."""

    async def __call__(self, path: Path) -> None:
        """
        Create a virtual environment at the given location.

        This runs `self.create` in a separate thread that can be awaited.

        Parameters
        ----------
        path : Path
            directory for the created venv

        """
        await to_thread(self.create, path)


class VirtualenvWrapper:
    """
    Build your virtual environments using the virtualenv package.

    The package can be found on pypi.
    Call instances of this class with a path to create a venv at the given location.
    """

    def __init__(self, args: Sequence[str]) -> None:
        """
        Build your virtual environments using the virtualenv package.

        Parameters
        ----------
        args : Sequence[str]
            Commandline arguments to pass to `virtualenv`.

        """
        self.args = args

        # check that virtualenv is installed
        import virtualenv  # noqa: F401

    async def __call__(self, path: Path) -> None:
        """Build the venv at the given location in a separate thread."""
        from virtualenv import cli_run

        await to_thread(cli_run, [*self.args, str(path)])


class VirtualPythonEnvironment(Environment):
    """
    An environment for running build commands in a python virtual environment.

    If you want to create the venv when this environment is entered you can
    provide a `creator` which will be called with the `venv` location to create
    the environment. You can use the :class:`VenvWrapper` and
    :class:`VirtualenvWrapper` classes for that.
    If `creator` isn't provided it is expected that a python venv already exists
    at the given location.

    Parameters
    ----------
    path : Path
        The location of the current revision.
    name : str
        The name of the environment (usually the name of the current revision).
    venv : Path
        The path of the python venv.
    creator : Callable[[Path], Any], optional
        A callable for creating the venv, by default None

    Attributes
    ----------
    path : Path
        The location of the current revision.
    name : str
        The name of the environment.
    venv : Path
        The path of the python venv.

    """

    def __init__(
        self,
        path: Path,
        name: str,
        venv: str | Path,
        *,
        creator: Callable[[Path], Any] | None = None,
    ):
        """
        Environment for building inside a python virtual environment.

        Parameters
        ----------
        path : Path
            The location of the current revision.
        name : str
            The name of the environment (usually the name of the current revision).
        venv : Path
            The path of the python venv.
        creator : Callable[[Path], Any], optional
            A callable for creating the venv, by default None

        """
        super().__init__(path, name)
        self.venv = Path(venv).resolve()
        self._creator = creator

    async def create_venv(self) -> None:
        """
        Create the virtual python environment.

        This calls `creator` if provided otherwise it does nothing.

        Override this to customize how and when the venv is created.
        """
        if self._creator:
            logger.info("Creating venv...")
            result = self._creator(self.venv)
            if isawaitable(result):
                await result

    async def __aenter__(self: Self) -> Self:
        """Set the build environment up."""
        await super().__aenter__()
        # create the virtualenv if creator is specified
        await self.create_venv()
        return self

    def activate(self, env: dict[str, str]) -> dict[str, str]:
        """
        Activate a python venv in a dictionary of environment variables.

        .. warning:: This modifies the given dictionary in-place.

        Parameters
        ----------
        env : dict[str, str]
            The environment variable mapping to update.

        Returns
        -------
        dict[str, str]
            The dictionary that was passed with `env`.

        """
        env["VIRTUAL_ENV"] = str(self.venv)
        env["PATH"] = str(self.venv / "bin") + ":" + env["PATH"]
        return env

    async def run(
        self, *cmd: str, **kwargs: Any
    ) -> Tuple[str | bytes | None, str | bytes | None, int]:
        """
        Run a OS process in the environment.

        This implementation passes the arguments to
        :func:`asyncio.create_subprocess_exec`. But alters `env` to
        activate the correct python venv. If a python venv is already activated
        this activation is overridden.

        Returns
        -------
        stdout : str | None
            The output of the command,
        stderr : str | None
            The error output of the command
        returncode : int | None
            The returncode of the command

        """
        # activate venv
        kwargs["env"] = self.activate(kwargs.get("env", os.environ).copy())
        return await super().run(*cmd, **kwargs)


class Poetry(VirtualPythonEnvironment):
    """
    Build Environment for isolated builds with poetry.

    Use this to use poetry to create an isolated python venv for each
    build and to install specific poetry dependency groups.

    Parameters
    ----------
    path : Path
        The path of the current revision.
    name : str
        The name of the environment (usually the name of the revision).
    args : Iterable[str]
        The cmd arguments to pass to `poetry install`.

    """

    def __init__(self, path: Path, name: str, *, args: Iterable[str]):
        """
        Build Environment for isolated builds using poetry.

        Parameters
        ----------
        path : Path
            The path of the current revision.
        name : str
            The name of the environment (usually the name of the revision).
        args : Iterable[str]
            The cmd arguments to pass to `poetry install`.

        """
        super().__init__(
            path,
            name,
            path / ".venv",  # placeholder, determined later
        )
        self.args = args

    async def __aenter__(self) -> Self:
        """
        Set the poetry venv up.

        Raises
        ------
        BuildError
            Running `poetry install` failed.

        """
        # create venv and install deps
        self.logger.info("`poetry install`")

        cmd: list[str] = ["poetry", "install"]
        cmd += self.args

        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)  # unset poetry env
        env["POETRY_VIRTUALENVS_IN_PROJECT"] = "False"
        venv_path = self.path / ".venv"
        i = 0
        while venv_path.exists():
            venv_path = self.path / f".venv-{i}"
            i += 1
        env["POETRY_VIRTUALENVS_PATH"] = str(venv_path)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.path,
            env=env,
            stdout=PIPE,
            stderr=PIPE,
        )
        out, err = await process.communicate()
        out = out.decode(errors="ignore")
        err = err.decode(errors="ignore")

        self.logger.debug("Installation output:\n %s", out)
        if process.returncode != 0:
            self.logger.error("Installation error:\n %s", err)
            raise BuildError from CalledProcessError(
                cast(int, process.returncode), " ".join(cmd), out, err
            )

        # ---- locate venv
        # In the previous process poetry will have created or
        # ensured the existence of a venv in `venv_path` path folder.
        # However the venv itself constitutes a subdirectory with
        # an arbitrary name generated by poetry.
        # Thus we ask poetry to give as the name of the venv folder.
        cmd: list[str] = ["poetry", "env", "info", "--path"]
        process = await asyncio.create_subprocess_exec(
            *cmd, cwd=self.path, env=env, stdout=PIPE, stderr=PIPE
        )
        out, err = await process.communicate()
        out = out.decode().rstrip("\n")
        err = err.decode(errors="ignore")

        self.logger.debug("Venv location: %s", out)
        if process.returncode != 0:
            self.logger.error("Error locating venv:\n %s", err)
            raise BuildError from CalledProcessError(
                cast(int, process.returncode), " ".join(cmd), out, err
            )
        self.venv = Path(out)  # actual venv location

        return self


class Pip(VirtualPythonEnvironment):
    """
    Build Environment for using a venv and installing deps with pip.

    Use this to run the build commands in a python virtual environment
    and install dependencies with pip into the venv before the build.

    Parameters
    ----------
    path : Path
        The path of the current revision.
    name : str
        The name of the environment (usually the name of the revision).
    venv : Path
        The path of the python venv.
    args : Iterable[str]
        The cmd arguments to pass to `pip install`.
    creator : Callable[[Path], Any] | None, optional
        A callable for creating the venv, by default None

    """

    def __init__(
        self,
        path: Path,
        name: str,
        venv: str | Path,
        *,
        args: Iterable[str],
        creator: Callable[[Path], Any] | None = None,
    ):
        """
        Build Environment for using a venv and pip.

        Parameters
        ----------
        path : Path
            The path of the current revision.
        name : str
            The name of the environment (usually the name of the revision).
        venv : Path
            The path of the python venv.
        args : Iterable[str]
            The cmd arguments to pass to `pip install`.
        creator : Callable[[Path], Any], optional
            A callable for creating the venv, by default None

        """
        super().__init__(path, name, venv, creator=creator)
        self.args = args

    async def __aenter__(self) -> Self:
        """
        Set the venv up.

        Raises
        ------
        BuildError
            Running `pip install` failed.

        """
        await super().__aenter__()

        logger.info("Running `pip install`...")

        cmd: list[str] = ["pip", "install"]
        cmd += self.args

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.path,
            env=self.activate(os.environ.copy()),
            stdout=PIPE,
            stderr=PIPE,
        )
        out, err = await process.communicate()
        out = out.decode(errors="ignore")
        err = err.decode(errors="ignore")

        self.logger.debug("Installation output:\n %s", out)
        if process.returncode != 0:
            raise BuildError from CalledProcessError(
                cast(int, process.returncode), " ".join(cmd), out, err
            )
        return self
