from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

from sphinx_polyversion.environment import Environment
from sphinx_polyversion.json import JSONable


class BuildError(Exception):
    """Building a specific version failed."""


ENV = TypeVar("ENV", bound=Environment)
R = TypeVar("R")


class Builder(Generic[ENV, R], metaclass=ABCMeta):
    @abstractmethod
    async def build(self, environment: ENV, output_dir: Path, data: JSONable) -> R:
        ...
