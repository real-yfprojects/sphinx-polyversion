"""Helpers for the other modules."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from functools import partial
from pathlib import PurePath
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Iterable,
    Set,
    TypeVar,
    cast,
)

if TYPE_CHECKING:
    from pathlib import Path

    from typing_extensions import ParamSpec

    P = ParamSpec("P")
    R = TypeVar("R")

if sys.version_info >= (3, 9):
    from asyncio import to_thread
else:

    async def to_thread(
        func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
    ) -> R:
        """
        Run a synchronous function asynchronously in a new thread.

        Parameters
        ----------
        func : Callable[P, R]
            The function to call.
        *args
            The arguments to call `func` with.
        **kwargs
            The keyword arguments to call `func` with.

        Returns
        -------
        The return value of the called function.

        """
        loop = asyncio.get_running_loop()
        func_call = partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)


PA = TypeVar("PA", bound=PurePath)


def shift_path(src_anchor: PA, dst_anchor: PA, src: PA) -> PA:
    """
    Shift a path from one anchor (root) directory to another.

    Parameters
    ----------
    src_anchor : Path
        The anchor
    dst_anchor : Path
        The destination
    src : Path
        The path to shift

    Returns
    -------
    Path
        The shifted path

    """
    return dst_anchor / src.relative_to(src_anchor)


def import_file(path: Path) -> Any:
    """
    Import a module from its location in the file system.

    Parameters
    ----------
    path : Path
        The location of the python file to import.

    Returns
    -------
    Any
        The imported module.

    Raises
    ------
    OSError
        The module spec couldn't be created.
    ImportError
        No loader was found for the module.

    """
    module_name = path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec:
        raise OSError(f"Failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    if not spec.loader:
        raise ImportError(f"Failed to load {path}")
    spec.loader.exec_module(module)

    return module


async def async_all(awaitables: Iterable[Awaitable[Any]]) -> bool:
    """
    Return True if all awaitables return True.

    If the iterator is empty, True is returned. The awaitables may
    return any value. These values are converted to boolean.

    Parameters
    ----------
    awaitables : Iterator[Awaitable[Any]]
        The awaitables to check.

    Returns
    -------
    bool
        Whether all awaitables returned True.

    """
    tasks = cast(
        Set["asyncio.Task[Any]"],
        {
            asyncio.create_task(aws) if asyncio.iscoroutine(aws) else aws
            for aws in awaitables
        },
    )
    while tasks:
        done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for finished_task in done:
            result = finished_task.result()

            if not result:
                # if one fails we already know the return value
                # cancel the other tasks
                for unfinished_task in tasks:
                    unfinished_task.cancel()
                if tasks:
                    await asyncio.wait(tasks)
                return False
    return True
