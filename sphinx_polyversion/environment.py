"""Build Environment Base API."""

from __future__ import annotations

import asyncio
from functools import partial
from logging import getLogger
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Tuple,
    Type,
    TypeVar,
    cast,
)

from sphinx_polyversion.log import ContextAdapter

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["Environment"]


class Environment:
    """
    A build environment and contextmanager to run commands in.

    This is a base class but it can be instanciated as well to have a
    environment that does nothing.

    Parameters
    ----------
    path : Path
        The location of the current revision.
    name : str
        The name of the environment (usually the name of the current revision).

    Methods
    -------
    run(*cmd: str, decode: bool = True, **kwargs: Any)
        Run a OS process in the environment.

    """

    path: Path

    def __init__(self, path: Path, name: str):
        """
        Init the build environment and contextmanager to run commands in.

        Parameters
        ----------
        path : Path
            The location of the current revision.
        name : str
            The name of the environment (usually the name of the current revision).

        """
        self.path = path.resolve()
        self.logger = ContextAdapter(getLogger(__name__), {"context": name})

    async def __aenter__(self: ENV) -> ENV:
        """Set the environment up."""
        return self

    async def __aexit__(self, *exc_info) -> bool | None:  # type: ignore[no-untyped-def]
        """Clean the environment up."""
        return None

    async def run(
        self, *cmd: str, decode: bool = True, **kwargs: Any
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
        process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        out, err = await process.communicate()
        if decode:
            out = out.decode(errors="ignore") if out is not None else None  # type: ignore[assignment]
            err = err.decode(errors="ignore") if err is not None else None  # type: ignore[assignment]
        return out, err, cast(int, process.returncode)

    @classmethod
    def factory(cls: Type[ENV], **kwargs: Any) -> Callable[[Path, str], ENV]:
        """
        Create a factory function for this environment class.

        This returns a factory that can be used with :class:`DefaultDriver`.
        This method works similiar to :func:`functools.partial`. The arguments
        passed to this function will be used by the factory to instantiate
        the actual environment class.

        Parameters
        ----------
        **kwargs
            Arguments to use when creating the instance.

        Returns
        -------
        Callable[[Path, str], ENV]
            The factory function.

        """
        return partial(cls, **kwargs)


ENV = TypeVar("ENV", bound=Environment)
