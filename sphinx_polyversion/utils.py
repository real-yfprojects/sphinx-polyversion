"""Helpers for the other modules."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from typing import TYPE_CHECKING, Callable, TypeVar

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


def shift_path(src_anchor: Path, dst_anchor: Path, src: Path) -> Path:
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
