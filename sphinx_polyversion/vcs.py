from abc import abstractmethod
from pathlib import Path
from typing import Iterable, Protocol, TypeVar, runtime_checkable

RT = TypeVar("RT")


@runtime_checkable
class VersionProvider(Protocol[RT]):
    @abstractmethod
    async def root(self, path: Path) -> Path:
        ...

    @abstractmethod
    async def checkout(self, root: Path, path: Path, revision: RT) -> None:
        ...

    @abstractmethod
    async def retrieve(self, root: Path) -> Iterable[RT]:
        ...
