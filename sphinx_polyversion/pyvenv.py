from __future__ import annotations

import asyncio
import os
from asyncio.subprocess import PIPE
from inspect import isawaitable
from logging import getLogger
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
    from pathlib import Path

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

        await to_thread(cli_run, [*self.args, path])


class VirtualPythonEnvironment(Environment):
    def __init__(
        self,
        path: Path,
        name: str,
        venv: Path,
        *,
        creator: Callable[[Path], Any] | None = None,
    ):
        super().__init__(path, name)
        self.venv = venv.resolve()
        self._creator = creator

    async def create_venv(self) -> None:
        if self._creator:
            logger.info("Creating venv...")
            result = self._creator(self.venv)
            if isawaitable(result):
                await result

    async def __aenter__(self: Self) -> Self:
        await super().__aenter__()
        # create the virtualenv if creator is specified
        await self.create_venv()
        return self

    def activate(self, env: dict[str, str]) -> dict[str, str]:
        env["VIRTUAL_ENV"] = str(self.venv)
        env["PATH"] = str(self.venv) + ":" + env["PATH"]
        return env

    async def run(
        self, *cmd: str, **kwargs: Any
    ) -> Tuple[str | bytes | None, str | bytes | None, int]:
        """
        Run a OS process in the environment.

        This implementation passes the arguments to
        :func:`asyncio.create_subprocess_exec`.

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
    def __init__(self, path: Path, name: str, *, args: Iterable[str]):
        super().__init__(path, name, path / ".venv")
        self.args = args

    async def __aenter__(self) -> Poetry:
        self.logger.info("`poetry install`")

        cmd: list[str] = ["poetry", "install"]
        cmd += self.args

        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)  # unset poetry env

        process = await asyncio.create_subprocess_exec(
            *cmd, cwd=self.path, env=env, stdout=PIPE, stderr=PIPE
        )
        out, err = await process.communicate()
        out = out.decode()
        err = err.decode()

        self.logger.debug("Installation output:\n %s", out)
        if process.returncode != 0:
            self.logger.error("Installation error:\n %s", err)
            raise BuildError from CalledProcessError(
                cast(int, process.returncode), " ".join(cmd), out, err
            )
        return self


class Pip(VirtualPythonEnvironment):
    def __init__(
        self,
        path: Path,
        name: str,
        venv: Path,
        *,
        args: Iterable[str],
        creator: Callable[[Path], Any] | None = None,
    ):
        super().__init__(path, name, venv, creator=creator)
        self.args = args

    async def __aenter__(self) -> Pip:
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
        out = out.decode()
        err = err.decode()

        self.logger.debug("Installation output:\n %s", out)
        if process.returncode != 0:
            raise BuildError from CalledProcessError(
                cast(int, process.returncode), " ".join(cmd), out, err
            )
        return self
