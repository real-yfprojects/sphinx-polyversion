from __future__ import annotations

import asyncio
import sys
import tempfile
from abc import ABCMeta, abstractmethod
from contextlib import AsyncExitStack, asynccontextmanager
from logging import getLogger
from pathlib import Path
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Callable,
    Generic,
    Iterable,
    List,
    Tuple,
    Type,
    TypeVar,
    cast,
)

from sphinx_polyversion.builder import Builder, BuildError
from sphinx_polyversion.environment import Environment
from sphinx_polyversion.json import JSONable

if TYPE_CHECKING:
    from sphinx_polyversion.vcs import VersionProvider

EXC_INFO = Tuple[Type[BaseException], BaseException, TracebackType]
ENV = TypeVar("ENV", bound=Environment)
RT = TypeVar("RT")

logger = getLogger(__name__)


class Driver(Generic[RT, ENV], metaclass=ABCMeta):
    vcs: VersionProvider[RT]
    output_dir: Path
    #: targeted revisions
    targets: Iterable[RT]
    #: revisions of successful builds
    builds: List[RT]

    def __init__(self, cwd: Path, output_dir: Path) -> None:
        self.cwd = cwd
        self.output_dir = output_dir
        self.builds = []

    @abstractmethod
    def name_for_rev(self, rev: RT) -> str:
        ...

    @abstractmethod
    async def init_vcs(self) -> VersionProvider[RT]:
        ...

    @abstractmethod
    async def init_builder(self, rev: RT) -> Builder[ENV, Any]:
        ...

    @abstractmethod
    async def init_environment(self, path: Path, rev: RT) -> ENV:
        ...

    @abstractmethod
    async def init_data(self, rev: RT, env: ENV) -> JSONable:
        ...

    @abstractmethod
    def tmp_dir(self, rev: RT) -> AsyncContextManager[Path]:
        ...

    @abstractmethod
    def build_failed(self, rev: RT, exc_info: EXC_INFO) -> None:
        ...

    def build_succeeded(self, rev: RT, data: Any) -> None:
        self.builds.append(rev)

    async def build_revision(self, rev: RT) -> None:
        builder = await self.init_builder(rev)

        try:
            async with AsyncExitStack() as stack:
                # create temporary directory to use for building this version
                path = await stack.enter_async_context(self.tmp_dir(rev))
                # copy source files
                await self.vcs.checkout(self.cwd, path, rev)
                # setup build environment (e.g. poetry/pip venv)
                env = cast(
                    ENV,
                    await stack.enter_async_context(
                        await self.init_environment(path, rev)
                    ),
                )
                # construct metadata to pass to the build process
                data = await self.init_data(rev, env)
                # build the docs
                artifact = await builder.build(
                    env, self.output_dir / self.name_for_rev(rev), data=data
                )
        except BuildError:
            # call hook for build error
            self.build_failed(rev, cast(EXC_INFO, sys.exc_info()))
        else:
            # call hook for success
            self.build_succeeded(rev, artifact)

    @abstractmethod
    async def build_root(self) -> None:
        ...

    async def init(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.vcs = await self.init_vcs()
        self.cwd = await self.vcs.root(self.cwd)
        self.targets = await self.vcs.retrieve(self.cwd)

    async def run(self) -> None:
        await self.init()
        await asyncio.gather(*(self.build_revision(rev) for rev in self.targets))
        await self.build_root()


JRT = TypeVar("JRT", bound=JSONable)


class DefaultDriver(Driver[JRT, ENV]):
    def __init__(
        self,
        cwd: Path,
        output_dir: Path,
        *,
        vcs: VersionProvider[JRT],
        builder: Builder[ENV, Any],
        env: Callable[[Path, str], ENV],
        namer: Callable[[RT], str],
    ) -> None:
        super().__init__(cwd, output_dir)
        self.vcs = vcs
        self.builder = builder
        self.env_factory = env
        self.namer = namer

    def name_for_rev(self, rev: RT) -> str:
        return self.namer(rev)

    async def init_vcs(self) -> VersionProvider[JRT]:
        return self.vcs

    async def init_builder(self, rev: JRT) -> Builder[ENV, Any]:
        return self.builder

    async def init_environment(self, path: Path, rev: JRT) -> ENV:
        return self.env_factory(path, self.name_for_rev(rev))

    async def init_data(self, rev: JRT, env: ENV) -> dict[str, JSONable]:  # type: ignore[override]
        return {"revisions": tuple(self.targets), "current": rev}

    @asynccontextmanager
    async def tmp_dir(self, rev: JRT) -> AsyncGenerator[Path, None]:
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def build_failed(self, rev: JRT, exc_info: EXC_INFO) -> None:
        logger.error("Building %s failed", self.name_for_rev(rev), exc_info=exc_info)

    async def build_root(self) -> None:
        (self.output_dir / "versions.json").write_text("help")
