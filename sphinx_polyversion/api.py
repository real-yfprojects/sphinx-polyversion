"""API to use in config files like `conf.py`."""

from __future__ import annotations

import os
from typing import Any

# load git module to be able to decode its classses
import sphinx_polyversion.git  # noqa: F401
from sphinx_polyversion.json import GLOBAL_DECODER


class LoadError(RuntimeError):
    """An error occurred during loading of the metadata."""


def load(namespace: dict[str, Any] | None = None) -> Any:
    """
    Load metadata and sphinx config vars.

    This loads the polyversion metadata about the current revision
    and more from the `POLYVERSION_DATA` environment variable.
    You can pass this method the `globals()` dictionary to load
    the needed sphinx config vars and make them available as global variables.

    Parameters
    ----------
    namespace : dict[str, Any] | None, optional
        The dictionary to load the data into, by default None

    Returns
    -------
    Any
        The data loaded from the env var.

    Raises
    ------
    LoadError
        The environment variable isn't set.
    """
    namespace = namespace or {}

    key = "POLYVERSION_DATA"
    if not (str_data := os.getenv(key)):
        raise LoadError(f"Env var {key} isn't set.")

    data = GLOBAL_DECODER.decode(str_data)

    html_context: dict[str, Any] = namespace.setdefault("html_context", {})
    if isinstance(data, dict):
        html_context.update(data)
    else:
        html_context["data"] = data

    return data
