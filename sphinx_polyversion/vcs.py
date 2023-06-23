"""Abstract version provider API."""

from abc import abstractmethod
from pathlib import Path
from typing import Iterable, Protocol, TypeVar, runtime_checkable

RT = TypeVar("RT")


@runtime_checkable
class VersionProvider(Protocol[RT]):
    """Base for classes providing target revisions of the docs to build."""

    @abstractmethod
    async def root(self, path: Path) -> Path:
        """
        Determine the root of the current project.

        Parameters
        ----------
        path : Path
            A path inside the project. (Usually the current working directory)

        Returns
        -------
        Path
            The root path of the project.
        """

    @abstractmethod
    async def checkout(self, root: Path, dest: Path, revision: RT) -> None:
        """
        Create copy of a specific revision at the given path.

        Parameters
        ----------
        root : Path
            The root path of the project.
        dest : Path
            The destination to extract the revision to.
        revision : Any
            The revision to extract.
        """

    @abstractmethod
    async def retrieve(self, root: Path) -> Iterable[RT]:
        """
        List all build targets.

        The build targets comprise all revisions that should be build.

        Parameters
        ----------
        root : Path
            The root path of the project.

        Returns
        -------
        Iterable[RT]
            The build targets.
        """
