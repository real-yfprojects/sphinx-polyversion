from __future__ import annotations

import logging
from typing import Any, MutableMapping


class ContextAdapter(logging.LoggerAdapter):  # type: ignore[type-arg]
    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        return "[%s] %s" % (self.extra["context"], msg), kwargs
