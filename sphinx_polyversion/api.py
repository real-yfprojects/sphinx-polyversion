from __future__ import annotations

import os
from typing import Any

# load git module to be able to decode its classses
import sphinx_polyversion.git  # noqa: F401
from sphinx_polyversion.json import GLOBAL_DECODER


class LoadError(RuntimeError):
    pass


def load(namespace: dict[str, Any] | None = None) -> Any:
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
