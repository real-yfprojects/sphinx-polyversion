from __future__ import annotations

import asyncio
import sys
from functools import partial
from typing import TYPE_CHECKING, Callable, TypeVar

if TYPE_CHECKING:
    from typing_extensions import ParamSpec

    P = ParamSpec("P")
    R = TypeVar("R")

if sys.version_info >= (3, 9):
    from asyncio import to_thread
else:

    async def to_thread(
        func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
    ) -> R:
        loop = asyncio.get_running_loop()
        func_call = partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)
