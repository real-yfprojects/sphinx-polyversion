"""Test the `utils` submodule."""

import asyncio
from pathlib import PurePath
from typing import TypeVar

import pytest

from sphinx_polyversion.utils import async_all, shift_path


@pytest.mark.parametrize(
    ("anchor1", "anchor2", "path", "solution"),
    [
        ("a", "b", "a/c", "b/c"),
        ("a", "b", "a/b/c", "b/b/c"),
        ("a/b", "a", "a/b/c", "a/c"),
        ("a/b", "b", "a/b/c/d", "b/c/d"),
    ],
)
def test_shift_path(anchor1, anchor2, path, solution):
    """Test the shift_path function."""
    assert shift_path(PurePath(anchor1), PurePath(anchor2), PurePath(path)) == PurePath(
        solution
    )


T = TypeVar("T")


def test_async_all():
    """Test the `async_all` implementation."""

    async def future(value: T) -> T:
        return value

    assert asyncio.run(async_all([]))

    all_true = [future(True) for i in range(8)]
    assert asyncio.run(async_all(all_true))

    all_false = [future(False) for i in range(8)]
    assert not asyncio.run(async_all(all_false))

    first_false = [future(False)] + [future(True) for i in range(8)]
    assert not asyncio.run(async_all(first_false))

    last_false = [future(True) for i in range(8)] + [future(False)]
    assert not asyncio.run(async_all(last_false))

    some_false = (
        [future(True) for i in range(5)]
        + [future(False)]
        + [future(True) for i in range(5)]
        + [future(False)]
        + [future(True) for i in range(5)]
    )
    assert not asyncio.run(async_all(some_false))
