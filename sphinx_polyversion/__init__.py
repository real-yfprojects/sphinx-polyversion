"""
Build multiple versions of your sphinx docs and merge them into one website.

Attributes
----------
logger: Logger
    The root logger used by this package.


"""
from logging import DEBUG, NullHandler, getLogger

from sphinx_polyversion.api import apply_overrides, load, order_versions
from sphinx_polyversion.driver import DefaultDriver
from sphinx_polyversion.json import GLOBAL_DECODER, GLOBAL_ENCODER

__all__ = (
    "apply_overrides",
    "load",
    "order_versions",
    "DefaultDriver",
    "GLOBAL_DECODER",
    "GLOBAL_ENCODER",
)

logger = getLogger(__name__)
logger.setLevel(DEBUG)
logger.addHandler(NullHandler())
