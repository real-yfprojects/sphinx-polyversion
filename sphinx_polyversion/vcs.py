"""Abstract version provider API."""

from abc import abstractmethod
from pathlib import Path
from typing import Iterable, Protocol, TypeVar, runtime_checkable

RT = TypeVar("RT")


@runtime_checkable
class VersionProvider(Protocol[RT]):
    """Base for classes providing target revisions of the docs to build."""

    def name(self, revision: RT) -> str:
        """
        Get the (unique) name of a revision.

        This name will usually be used for creating the subdirectories
        of the revision.

        Parameters
        ----------
        root : Path
            The root path of the project.
        revision : Any
            The revision whose name is requested.

        Returns
        -------
        str
            The name of the revision.

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
