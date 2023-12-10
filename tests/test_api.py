"""Test the api exposed to conf.py and poly.py files."""


import json
import os
import sys

import pytest

from sphinx_polyversion.api import LoadError, apply_overrides, load


def test_load():
    """Test the `load` function."""
    # test that the function raises an error if the env var isn't set
    with pytest.raises(LoadError):
        load()

    # test that the function returns the data from the env var
    data = {"a": 1, "b": 2}
    os.environ["POLYVERSION_DATA"] = json.dumps(data)
    assert load() == data


def test_apply_overrides():
    """Test the `apply_overrides` function."""
    # override sys.argv add overrides
    sys.argv = ["poly.py", "--override", "a=1", "--override", "b=2"]

    # test that the function applies the overrides
    namespace = {}
    apply_overrides(namespace)

    assert namespace == {"a": "1", "b": "2", "MOCK": False}
