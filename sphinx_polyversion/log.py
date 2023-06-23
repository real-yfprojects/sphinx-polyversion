"""Utilities for logging."""

from __future__ import annotations

import logging
from typing import Any, MutableMapping


class ContextAdapter(logging.LoggerAdapter):  # type: ignore[type-arg]
    """A adapter adding arbitrary context information to a log message."""

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        """
        Process the message of a logging call.

        Process the logging message and keyword arguments passed in to a
        logging call to insert contextual information.
        You can either manipulate the message itself,
        the keyword args or both. Return the message and kwargs modified
        (or not) to suit your needs.
        """
        return "[%s] %s" % (self.extra["context"], msg), kwargs
