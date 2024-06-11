"""The core logic of this tool and orchestrator of everything."""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from abc import ABCMeta, abstractmethod
from contextlib import AsyncExitStack, asynccontextmanager
from inspect import isawaitable
from logging import getLogger
from pathlib import Path
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Callable,
    Coroutine,
    Generic,
    Iterable,
    List,
    Mapping,
    Tuple,
    Type,
    TypedDict,
    TypeVar,
    Union,
    cast,
)

from sphinx_polyversion.builder import Builder, BuildError
from sphinx_polyversion.environment import Environment
from sphinx_polyversion.json import GLOBAL_ENCODER, Encoder, JSONable
from sphinx_polyversion.utils import shift_path

if TYPE_CHECKING:
    from os import PathLike

    from sphinx_polyversion.vcs import VersionProvider

    StrPath = Union[str, PathLike[str]]


__all__ = ["Driver", "DefaultDriver"]


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
    mock : MockData[RT] | None | Literal[False], optional
        Only build from local files and mock building all docs using the data provided.

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

    def __init__(
        self,
        root: Path,
        output_dir: Path,
        *,
        mock: MockData | None = None,
    ) -> None:
        """
        Init the driver.

        Parameters
        ----------
        root : Path
            The current working directory
        output_dir : Path
            The directory where to place the built docs.
        mock : MockData[RT] | None | Literal[False], optional
            Only build from local files and mock building all docs using the data provided.

        """
        self.root = root
        self.output_dir = output_dir
        self.builds = []
        self.mock = mock

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
                await self.vcs.checkout(self.root, path, rev)
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

    async def build_local(self) -> None:
        """
        Build the local version only.

        Raises
        ------
        ValueError
            `self.mock` isn't set.

        """
        if not self.mock:
            raise ValueError("Missing mock data.")

        # process mock data
        self.targets = self.builds = self.mock["revisions"]
        rev = self.mock["current"]

        if rev not in self.targets:
            self.targets.append(rev)

        # create builder
        builder = await self.init_builder(rev)

        # create temporary directory to use for building this version
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            # copy source files
            logger.info("Copying source files...")
            shutil.copytree(self.root, path, symlinks=True, dirs_exist_ok=True)
            # setup build environment (e.g. poetry/pip venv)
            async with await self.init_environment(path, rev) as env:
                # construct metadata to pass to the build process
                data = await self.init_data(rev, env)
                # build the docs
                artifact = await builder.build(
                    env, self.output_dir / "local", data=data
                )

        # call hook for success, on failure an exception will have been raised
        self.build_succeeded(rev, artifact)

        await self.build_root()

    async def init(self) -> None:
        """Prepare the building."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.vcs = await self.init_vcs()
        self.targets = await self.vcs.retrieve(self.root)

    async def arun(self) -> None:
        """Build all revisions (async)."""
        await self.init()
        await asyncio.gather(*(self.build_revision(rev) for rev in self.targets))
        await self.build_root()

    def run(self, mock: bool = False) -> None:
        """Build all revisions or build from local files."""
        if mock:
            asyncio.run(self.build_local())
        else:
            asyncio.run(self.arun())


class MockData(TypedDict):
    current: Any
    revisions: list[Any]


JRT = TypeVar("JRT", bound=JSONable)
S = TypeVar("S")


class DefaultDriver(Driver[JRT, ENV], Generic[JRT, ENV, S]):
    """
    Simple driver implementation.

    This convenience class allows creating a driver from a version provider,
    a builder and an Environment factory.

    You can provide a dict for `env`, `data_factory` or `builder` that maps
    revisions to builders. In that case you must also provide a `selector`
    that is used to determine the closest key in the dict for the revision to
    build. This key is then used to get the builder or environment factory
    from the dict provided.

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
    data_factory : Callable[[DefaultDriver[JRT, ENV, S], JRT, ENV], JSONable], optional
        A callable returning the data to pass to the builder.
    root_data_factory : Callable[[DefaultDriver[JRT, ENV, S]], dict[str, Any]], optional
        A callable returning the variables to pass to the jinja templates.
    namer : Callable[[RT], str], optional
        A callable determining the name of a revision.
    selector: Callable[[JRT, Iterable[S]], S | Coroutine[Any, Any, S]], optional
        The selector to use when either `env` or `builder` are a dict.
    encoder : Encoder, optional
        The encoder to use for dumping `versions.json` to the output dir.
    static_dir : Path, optional
        The source directory for root level static files.
    template_dir : Path, optional
        The source directory for root level templates.
    mock : MockData[RT] | None | Literal[False], optional
        Only build from local files and mock building all docs using the data provided.

    """

    def __init__(
        self,
        root: StrPath,
        output_dir: StrPath,
        *,
        vcs: VersionProvider[JRT],
        builder: Builder[ENV, Any] | Mapping[S, Builder[ENV, Any]],
        env: Callable[[Path, str], ENV] | Mapping[S, Callable[[Path, str], ENV]],
        namer: Callable[[JRT], str] | None = None,
        selector: Callable[[JRT, Iterable[S]], S | Coroutine[Any, Any, S]]
        | None = None,
        data_factory: Callable[[DefaultDriver[JRT, ENV, S], JRT, ENV], JSONable]
        | Mapping[S, Callable[[DefaultDriver[JRT, ENV, S], JRT, ENV], JSONable]]
        | None = None,
        root_data_factory: Callable[[DefaultDriver[JRT, ENV, S]], dict[str, Any]]
        | None = None,
        encoder: Encoder | None = None,
        static_dir: StrPath | None = None,
        template_dir: StrPath | None = None,
        mock: MockData | None = None,
    ) -> None:
        """
        Init the driver.

        Parameters
        ----------
        root : Path
            The current working directory
        output_dir : Path
            The directory where to place the built docs.
        vcs : VersionProvider[JRT]
            The version provider to use.
        builder : Builder[ENV, Any]
            The builder to use.
        env : Callable[[Path, str], ENV]
            A factory producing the environments to use.
        data_factory : Callable[[DefaultDriver[JRT, ENV, S], JRT, ENV], JSONable], optional
            A callable returning the data to pass to the builder.
        root_data_factory : Callable[[DefaultDriver[JRT, ENV, S]], dict[str, Any]], optional
            A callable returning the variables to pass to the jinja templates.
        namer : Callable[[JRT], str], optional
            A callable determining the name of a revision.
        selector: Callable[[JRT, Iterable[S]], S | Coroutine[Any, Any, S]], optional
            The selector to use when either `env` or `builder` are a dict.
        encoder : Encoder, optional
            The encoder to use for dumping `versions.json` to the output dir.
        static_dir : Path, optional
            The source directory for root level static files.
        template_dir : Path, optional
            The source directory for root level templates.
        mock : MockData[RT] | None | Literal[False], optional
            Only build from local files and mock building all docs using the data provided.

        """
        super().__init__(Path(root), Path(output_dir), mock=mock)
        self.static_dir = Path(static_dir) if static_dir is not None else static_dir
        self.template_dir = (
            Path(template_dir) if template_dir is not None else template_dir
        )
        self.vcs = vcs
        self.builder = builder
        self.env_factory = env
        self.data_factory = data_factory
        self.namer = namer
        self.encoder = encoder or GLOBAL_ENCODER
        self.root_data_factory = root_data_factory

        if isinstance(builder, dict) or isinstance(env, dict) and not selector:
            raise ValueError(
                "Must provide selector if a mapping is passed for `builder` or `env`."
            )
        self.selector = selector

    def name_for_rev(self, rev: JRT) -> str:
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
        return self.namer(rev) if self.namer else self.vcs.name(rev)

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
        if isinstance(self.builder, Mapping):
            r = self.selector(rev, self.builder.keys())  # type: ignore[misc]
            if isawaitable(r):
                r = await r
            return self.builder[cast(S, r)]
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
        if isinstance(self.env_factory, Mapping):
            r = self.selector(rev, self.env_factory.keys())  # type: ignore[misc]
            if isawaitable(r):
                r = await r
            f = self.env_factory[cast(S, r)]
        else:
            f = self.env_factory
        return f(path, self.name_for_rev(rev))

    async def init_data(self, rev: JRT, env: ENV) -> JSONable:
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
        if not self.data_factory:
            return {"revisions": tuple(self.targets), "current": rev}
        if isinstance(self.data_factory, Mapping):
            r = self.selector(rev, self.data_factory.keys())  # type: ignore[misc]
            if isawaitable(r):
                r = await r
            return self.data_factory[cast(S, r)](self, rev, env)
        return self.data_factory(self, rev, env)

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
        # metadata as json
        (self.output_dir / "versions.json").write_text(self.encoder.encode(self.builds))

        # copy static files
        if self.static_dir and self.static_dir.exists():
            logger.info("Copying static files to root directory...")
            for file in self.static_dir.rglob("*"):
                shutil.copyfile(
                    file, shift_path(self.static_dir, self.output_dir, file)
                )

        # generate dynamic files from jinja templates
        if self.root_data_factory:
            context = self.root_data_factory(self)
        else:
            context = {"revisions": self.builds, "repo": self.root}

        if self.template_dir and self.template_dir.is_dir():
            logger.info("Rendering jinja2 templates...")
            import jinja2

            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(self.template_dir)),
                autoescape=jinja2.select_autoescape(),
            )
            for template_path_str in env.list_templates():
                template = env.get_template(template_path_str)
                rendered = template.render(context)
                output_path = self.output_dir / template_path_str
                output_path.write_text(rendered)
