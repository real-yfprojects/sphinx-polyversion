"""Test the `utils` submodule."""

from pathlib import PurePath

import pytest

from sphinx_polyversion.utils import shift_path


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
