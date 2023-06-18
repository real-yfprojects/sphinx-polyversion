from logging import DEBUG, NullHandler, getLogger

logger = getLogger(__name__)
logger.setLevel(DEBUG)
logger.addHandler(NullHandler())
