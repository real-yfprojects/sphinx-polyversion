"""Abstract Building framework."""

from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

from sphinx_polyversion.environment import Environment
from sphinx_polyversion.json import JSONable

__all__ = ["BuildError", "Builder"]


class BuildError(Exception):
    """Building a specific version failed."""


ENV = TypeVar("ENV", bound=Environment)
R = TypeVar("R")


class Builder(Generic[ENV, R], metaclass=ABCMeta):
    """Base class for builders creating a documentation from source files."""

    @abstractmethod
    async def build(self, environment: ENV, output_dir: Path, data: JSONable) -> R:
        """
        Build and render a documentation.

        This method should actually carry out the work of building and rendering
        a documentation.

        Parameters
        ----------
        environment : Environment
            The environment to use for building.
        output_dir : Path
            The output directory to build to.
        data : JSONable
            The metadata to use for building.

        Returns
        -------
        Any
            Arbitrary data that results from building.
            This data can be used by custom :class:`Driver` implementations.

        """
        ...
