"""
Build multiple versions of your sphinx docs and merge them into one website.

Attributes
----------
logger: Logger
    The root logger used by this package.

"""
from logging import DEBUG, NullHandler, getLogger

from sphinx_polyversion.api import *  # noqa: F403
from sphinx_polyversion.driver import *  # noqa: F403

logger = getLogger(__name__)
logger.setLevel(DEBUG)
logger.addHandler(NullHandler())
