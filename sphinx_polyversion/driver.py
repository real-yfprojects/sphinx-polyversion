"""The core logic of this tool and orchestrator of everything."""

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
    """
    Base driver class.

    The driver orchestrates all operations and provides the core logic.
    The default implementation is :class:`DefaultDriver`.

    Parameters
    ----------
    cwd : Path
        The current working directory
    output_dir : Path
        The directory where to place the built docs.

    Methods
    -------
    run()
        Build all revisions.
    """

    #: The version provider used by the driver e.g. to determine build targets.
    vcs: VersionProvider[RT]
    #: Directory for the built docs.
    output_dir: Path
    #: Revisions targeted to be build.
    targets: Iterable[RT]
    #: Revisions of successful builds.
    builds: List[RT]

    def __init__(self, cwd: Path, output_dir: Path) -> None:
        """
        Init the driver.

        Parameters
        ----------
        cwd : Path
            The current working directory
        output_dir : Path
            The directory where to place the built docs.
        """
        self.cwd = cwd
        self.output_dir = output_dir
        self.builds = []

    @abstractmethod
    def name_for_rev(self, rev: RT) -> str:
        """
        Determine the name of a revision.

        Parameters
        ----------
        rev : Any
            The revision

        Returns
        -------
        str
            The name
        """

    @abstractmethod
    async def init_vcs(self) -> VersionProvider[RT]:
        """
        Return a version provider.

        The returned instance will be used by the driver to determine
        the revisions to build.

        Returns
        -------
        VersionProvider
        """

    @abstractmethod
    async def init_builder(self, rev: RT) -> Builder[ENV, Any]:
        """
        Get the builder for a specific revision.

        A different builder may be returned for each revision but the same
        builder can be used for multiple revisions as well.

        Parameters
        ----------
        rev : Any
            The revision the builder will be used for.

        Returns
        -------
        Builder
        """

    @abstractmethod
    async def init_environment(self, path: Path, rev: RT) -> ENV:
        """
        Initialize the build environment for a revision and path.

        The environment will be used to build the given revision and
        the path specifies the location where the revision is checked out.

        Parameters
        ----------
        path : Path
            The location of the revisions files.
        rev : Any
            The revision the environment is used for.

        Returns
        -------
        Environment
        """

    @abstractmethod
    async def init_data(self, rev: RT, env: ENV) -> JSONable:
        """
        Get the serializable metadata object for a revision.

        Parameters
        ----------
        rev : Any
            The revision the metadata should be bundled for.
        env : Environment
            The environment for the given revision.

        Returns
        -------
        JSONable
            The metadata to pass to the builder.
        """

    @abstractmethod
    def tmp_dir(self, rev: RT) -> AsyncContextManager[Path]:
        """
        Create a temporary directory for a revision.

        This directory is used to check the files of the revision out
        and for building. The context manager returned by this method should
        in turn return the path of the temporary directory created.

        Parameters
        ----------
        rev : Any
            The revision to be build in the directory.

        Returns
        -------
        AsyncContextManager[Path]
            A context manager creating and cleaning up the temp dir.
        """

    @abstractmethod
    def build_failed(self, rev: RT, exc_info: EXC_INFO) -> None:
        """
        Handle a failed build.

        This is a hook for a build fail.

        Parameters
        ----------
        rev : Any
            The revision that failed to build.
        exc_info : EXC_INFO
            The exception raised by the build steps.
        """

    def build_succeeded(self, rev: RT, data: Any) -> None:
        """
        Handle a successful build.

        This is a hook for a build success. This appends the revision
        to :attr:`builds`.

        Parameters
        ----------
        rev : Any
            The revision that was build.
        data : Any
            The data returned by the builder.
        """
        self.builds.append(rev)

    async def build_revision(self, rev: RT) -> None:
        """
        Build a revision.

        This does all the work of creating a temporary directory,
        copying the files of the given revision to that directory, creating
        an :class:`Environment` and calling the :class:`Builder`.

        Parameters
        ----------
        rev : Any
            The revision to build.
        """
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
        """
        Build the root directory.

        The root of the output directory contains subdirectories for the docs
        of each revision. This method adds more to this root directory.
        """

    async def init(self) -> None:
        """Prepare the building."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.vcs = await self.init_vcs()
        self.cwd = await self.vcs.root(self.cwd)
        self.targets = await self.vcs.retrieve(self.cwd)

    async def run(self) -> None:
        """Build all revisions."""
        await self.init()
        await asyncio.gather(*(self.build_revision(rev) for rev in self.targets))
        await self.build_root()


JRT = TypeVar("JRT", bound=JSONable)


class DefaultDriver(Driver[JRT, ENV]):
    """
    Simple driver implementation.

    This convenience class allows creating a driver from a version provider,
    a builder and an Environment factory.
    """

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
        """
        Init the driver.

        Parameters
        ----------
        cwd : Path
            The current working directory
        output_dir : Path
            The directory where to place the built docs.
        vcs : VersionProvider[JRT]
            The version provider to use.
        builder : Builder[ENV, Any]
            The builder to use.
        env : Callable[[Path, str], ENV]
            A factory producing the environments to use.
        namer : Callable[[RT], str]
            A callable determining the name of a revision.
        """
        super().__init__(cwd, output_dir)
        self.vcs = vcs
        self.builder = builder
        self.env_factory = env
        self.namer = namer

    def name_for_rev(self, rev: RT) -> str:
        """
        Determine the name of a revision.

        Parameters
        ----------
        rev : Any
            The revision

        Returns
        -------
        str
            The name
        """
        return self.namer(rev)

    async def init_vcs(self) -> VersionProvider[JRT]:
        """Prepare the building."""
        return self.vcs

    async def init_builder(self, rev: JRT) -> Builder[ENV, Any]:
        """
        Get the builder for a specific revision.

        A different builder may be returned for each revision but the same
        builder can be used for multiple revisions as well.

        Parameters
        ----------
        rev : Any
            The revision the builder will be used for.

        Returns
        -------
        Builder
        """
        return self.builder

    async def init_environment(self, path: Path, rev: JRT) -> ENV:
        """
        Initialize the build environment for a revision and path.

        The environment will be used to build the given revision and
        the path specifies the location where the revision is checked out.

        Parameters
        ----------
        path : Path
            The location of the revisions files.
        rev : Any
            The revision the environment is used for.

        Returns
        -------
        Environment
        """
        return self.env_factory(path, self.name_for_rev(rev))

    async def init_data(self, rev: JRT, env: ENV) -> dict[str, JSONable]:  # type: ignore[override]
        """
        Get the serializable metadata object for a revision.

        This bundles a list of all revisions and a the current revision into
        a dictionary:

        ..code::

            {"revisions": (*TARGETS), "current": REV}

        Parameters
        ----------
        rev : Any
            The revision the metadata should be bundled for.
        env : Environment
            The environment for the given revision.

        Returns
        -------
        JSONable
            The metadata to pass to the builder.
        """
        return {"revisions": tuple(self.targets), "current": rev}

    @asynccontextmanager
    async def tmp_dir(self, rev: JRT) -> AsyncGenerator[Path, None]:
        """
        Create a temporary directory for a revision.

        This directory is used to check the files of the revision out
        and for building. The context manager returned by this method should
        in turn return the path of the temporary directory created.

        This implementation creates a temporary directory using :mod:`tempfile`.

        Parameters
        ----------
        rev : Any
            The revision to be build in the directory.

        Returns
        -------
        AsyncContextManager[Path]
            A context manager creating and cleaning up the temp dir.
        """
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def build_failed(self, rev: JRT, exc_info: EXC_INFO) -> None:
        """
        Handle a failed build.

        This logs the error.

        Parameters
        ----------
        rev : Any
            The revision that failed to build.
        exc_info : EXC_INFO
            The exception raised by the build steps.
        """
        logger.error("Building %s failed", self.name_for_rev(rev), exc_info=exc_info)

    async def build_root(self) -> None:
        """
        Build the root directory.

        The root of the output directory contains subdirectories for the docs
        of each revision. This method adds more to this root directory.
        """
        # TODO: Implement root render
