"""API to use in config files like `conf.py`."""

from __future__ import annotations

import os
import re
from typing import Any

from sphinx_polyversion.json import GLOBAL_DECODER
from sphinx_polyversion.main import get_parser

__all__ = ["load", "apply_overrides"]


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


def apply_overrides(namespace: dict[str, Any]) -> dict[str, Any]:
    """
    Override global config vars with values provided from the cmd line.

    You will usually want to pass `globals()`.

    Parameters
    ----------
    namespace : dict[str, Any]
        The dictionary to alter.

    Returns
    -------
    dict[str, Any]
        The values that were applied to the namespace.

    """
    args = get_parser(expect_config=False).parse_args()
    overrides: dict[str, Any] = args.override
    if args.out:
        overrides["OUTPUT_DIR"] = args.out
    overrides.setdefault("MOCK", False)
    if args.local:
        overrides["MOCK"] = True
    namespace.update(overrides)
    return overrides


def order_versions(name: str, form_regex: str) -> tuple[str, ...]:
    match = re.fullmatch(form_regex, name)
    if not match:
        raise ValueError(f"Tag {name} doesn't match supplied format.")
    return match.groups()
