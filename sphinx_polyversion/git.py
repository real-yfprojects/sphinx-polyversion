"""Git VCS support."""

from __future__ import annotations

import asyncio
import enum
import re
import subprocess
import tarfile
import tempfile
from asyncio.subprocess import PIPE
from datetime import datetime
from functools import total_ordering
from inspect import isawaitable
from logging import getLogger
from pathlib import Path, PurePath
from subprocess import DEVNULL, CalledProcessError
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Coroutine,
    Iterable,
    Iterator,
    NamedTuple,
    Tuple,
    TypeVar,
    cast,
)

from sphinx_polyversion.json import GLOBAL_DECODER
from sphinx_polyversion.utils import async_all
from sphinx_polyversion.vcs import VersionProvider

__all__ = ["GitRef", "GitRefType", "Git", "file_predicate", "refs_by_type"]

logger = getLogger(__name__)

# -- Low level Git functions -------------------------------------------------


async def _get_git_root(directory: Path) -> Path:
    """
    Determine the root folder of the current git repo.

    Parameters
    ----------
    directory : Path
        Any directory in the repo.

    Returns
    -------
    Path
        The root folder.

    """
    cmd = (
        "git",
        "rev-parse",
        "--show-toplevel",
    )
    process = await asyncio.create_subprocess_exec(*cmd, cwd=directory, stdout=PIPE)
    out, err = await process.communicate()
    return Path(out.decode().rstrip("\n"))


regex_ref = r"refs/(?P<type>\w+|remotes/(?P<remote>[^/]+))/(?P<name>\S+)"
pattern_ref = re.compile(regex_ref)

GIT_FORMAT_STRING = "%(objectname)\t%(refname)\t%(creatordate:iso)"


def _parse_ref(line: str) -> GitRef | None:
    obj, ref, date_str = line.split("\t")
    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")

    match = pattern_ref.fullmatch(ref)
    if not match:
        logger.warning("Invalid ref %s", ref)
        return None
    name = match["name"]
    type_str = match["type"]
    remote = None
    if type_str == "heads":
        type_ = GitRefType.BRANCH
    elif type_str == "tags":
        type_ = GitRefType.TAG
    elif match["remote"]:
        type_ = GitRefType.BRANCH
        remote = match["remote"]
    else:
        logger.info("Ignoring ref %s", ref)
        return None

    return GitRef(name, obj, ref, type_, date, remote)


def get_current_commit(repo: Path) -> str:
    """
    Determine the hash of the currently checkedout commit.

    Parameters
    ----------
    repo : Path
        The git repository.

    Returns
    -------
    str
        The hex obj hash of the commit.

    """
    cmd = (
        "git",
        "rev-parse",
        "HEAD",
    )

    process = subprocess.run(cmd, stdout=PIPE, cwd=repo, check=True)
    return process.stdout.decode().rstrip("\n")


async def _get_all_refs(
    repo: Path, pattern: str = "refs"
) -> AsyncGenerator[GitRef, None]:
    """
    Get a list of refs (tags/branches) for a git repo.

    Parameters
    ----------
    repo : Path
        The repo to return the refs for
    pattern : str
        The pattern of refs to retrieve. Passed to `git for-each-ref`.

    Yields
    ------
    GitRef: The refs

    Raises
    ------
    ValueError
        Unknown ref type returned by git

    """
    cmd = (
        "git",
        "for-each-ref",
        "--format",
        GIT_FORMAT_STRING,
        pattern,
    )
    process = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, cwd=repo)
    out, err = await process.communicate()
    lines = out.decode().splitlines()
    for line in lines:
        ref = _parse_ref(line)
        if ref is not None:
            yield ref


async def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    cmd = (
        "git",
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
    )
    process = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, cwd=repo)
    out, err = await process.communicate()
    rc = cast(int, process.returncode)
    if rc > 1:
        raise CalledProcessError(rc, " ".join(cmd), stderr=err)
    return rc == 0


async def _copy_tree(
    repo: Path, ref: str, dest: str | Path, buffer_size: int = 0
) -> None:
    """
    Copy the contents of a ref into a location in the file system.

    Parameters
    ----------
    repo : Path
        The repo of the ref
    ref : str
        The ref
    dest : Union[str, Path]
        The destination to copy the contents to
    buffer_size : int
        The buffer size in memory which is filled before
        a temporary file is used for retrieving the contents. Defaults to 0.

    Raises
    ------
    CalledProcessError
        The git process exited with an error.

    """
    # retrieve commit contents as tar archive
    cmd = ("git", "archive", "--format", "tar", ref)
    with tempfile.SpooledTemporaryFile(max_size=buffer_size) as f:
        process = await asyncio.create_subprocess_exec(
            *cmd, cwd=repo, stdout=f, stderr=PIPE
        )
        out, err = await process.communicate()
        if process.returncode:
            raise CalledProcessError(process.returncode, " ".join(cmd), stderr=err)
        # extract tar archive to dir
        f.seek(0)
        with tarfile.open(fileobj=f) as tf:
            tf.extractall(str(dest))


async def file_exists(repo: Path, ref: GitRef, file: PurePath) -> bool:
    """
    Check whether a file exists in a given ref.

    Parameters
    ----------
    repo : Path
        The repo of the ref
    ref : GitRef
        The ref
    file : PurePath
        The file to check for

    Returns
    -------
    bool
        Whether the file was found in the contents of the ref

    """
    cmd = (
        "git",
        "cat-file",
        "-e",
        "{}:{}".format(ref.obj, file.as_posix()),
    )
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=repo,
        stdout=DEVNULL,
        stderr=DEVNULL,
    )
    rc = await process.wait()
    return rc == 0


# -- VersionProvider API -----------------------------------------------------


async def closest_tag(root: Path, ref: GitRef, tags: tuple[str]) -> str | None:
    """
    Find the closest ancestor to a given ref.

    Parameters
    ----------
    root : Path
        The repository root.
    ref : GitRef
        The ref to find the ancestor for.
    tags : tuple[str]
        A list of git references to map to.

    Returns
    -------
    str | None
        The closest ancestor or None if no ancestor was found.

    """
    for tag in reversed(tags):
        if await _is_ancestor(root, tag, ref.obj):
            return tag
    return None


S = TypeVar("S")


@GLOBAL_DECODER.register
class GitRefType(enum.Enum):
    """Types of git refs."""

    TAG = enum.auto()
    BRANCH = enum.auto()

    def _json_fields(self) -> str:
        return self.name

    @classmethod
    def _from_json_fields(cls, o: str) -> GitRefType:
        return cls[o]


@GLOBAL_DECODER.register
@total_ordering
class GitRef(NamedTuple):
    """A git ref representing a possible doc version."""

    name: str  # tag or branch name
    obj: str  # hash
    ref: str  # git ref
    type_: GitRefType
    date: datetime  # creation
    remote: str | None = None  # if remote ref: name of the remote

    def _json_fields(self) -> tuple[Any, ...]:
        return tuple(self)

    @classmethod
    def _from_json_fields(cls, o: Any) -> GitRef:
        return cls(*o)

    def __lt__(self, other: GitRef) -> bool:  # type: ignore[override]
        """Lower than."""
        return self.date < other.date


def refs_by_type(refs: Iterator[GitRef]) -> Tuple[list[GitRef], list[GitRef]]:
    """
    Group refs by type.

    Parameters
    ----------
    refs : Iterator[GitRef]
        The refs to group.

    Returns
    -------
    branches : list[GitRef]
    tags : list[GitRef]

    """
    return (
        list(filter(lambda r: r.type_ == GitRefType.BRANCH, refs)),
        list(filter(lambda r: r.type_ == GitRefType.TAG, refs)),
    )


def file_predicate(
    files: Iterable[str | PurePath],
) -> Callable[[Path, GitRef], Coroutine[None, None, bool]]:
    """
    Return a predicate that checks for files in a git revision.

    The returned predicate calls :func:`file_exists` for each file and
    checks whether all files exists in a given revision.

    Parameters
    ----------
    files : Iterable[str  |  PurePath]
        The files to check for.

    Returns
    -------
    Callable[[Path, GitRef], Coroutine[None, None, bool]]
        The predicate.

    """
    files = [PurePath(file) for file in files]

    async def predicate(repo: Path, ref: GitRef) -> bool:
        return await async_all(file_exists(repo, ref, file) for file in files)  # type: ignore[arg-type]

    return predicate


class Git(VersionProvider[GitRef]):
    """
    Provide versions from git repository.

    Parameters
    ----------
    branch_regex : str | re.Pattern
        Regex branches must match completely
    tag_regex : str | re.Pattern
        Regex tags must match completely
    remote : str | None, optional
        Limit to this remote or to local refs if not specified, by default None

    """

    def __init__(
        self,
        branch_regex: str | re.Pattern[Any],
        tag_regex: str | re.Pattern[Any],
        remote: str | None = None,
        *,
        predicate: Callable[[Path, GitRef], bool | Awaitable[bool]] | None = None,
        buffer_size: int = 0,
    ) -> None:
        """Init."""
        super().__init__()
        self.remote = remote
        self.buffer_size = buffer_size

        if isinstance(branch_regex, str):
            branch_regex = re.compile(branch_regex)
        if isinstance(tag_regex, str):
            tag_regex = re.compile(tag_regex)
        self.branch_regex = branch_regex
        self.tag_regex = tag_regex

        self._predicate = predicate

    def name(self, revision: GitRef) -> str:
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
        return revision.name

    @staticmethod
    async def aroot(path: str | Path) -> Path:
        """
        Determine the root of the current git repository (async).

        Parameters
        ----------
        path : Path
            A path inside the repo. (Usually the current working directory)

        Returns
        -------
        Path
            The root path of the repo.

        """
        return await _get_git_root(Path(path))

    @classmethod
    def root(cls, path: str | Path) -> Path:
        """
        Determine the root of the current git repository.

        Parameters
        ----------
        path : Path
            A path inside the repo. (Usually the current working directory)

        Returns
        -------
        Path
            The root path of the repo.

        """
        return asyncio.run(cls.aroot(path))

    async def checkout(self, root: Path, dest: Path, revision: GitRef) -> None:
        """
        Extract a specific revision to the given path.

        Parameters
        ----------
        root : Path
            The root path of the git repository.
        dest : Path
            The destination to copy the revision to.
        revision : Any
            The revision to extract.

        """
        await _copy_tree(root, revision.obj, dest, self.buffer_size)

    async def predicate(self, root: Path, ref: GitRef) -> bool:
        """
        Check whether a revision should be build.

        This predicate is used by :method:`retrieve` to filter the
        git references retrieved.

        Parameters
        ----------
        root : Path
            The root path of the git repo.
        ref : GitRef
            The git reference to check.

        Returns
        -------
        bool
            Whether to build the revision referenced.

        """
        match = True
        if ref.type_ == GitRefType.TAG:
            match = bool(self.tag_regex.fullmatch(ref.name))
        if ref.type_ == GitRefType.BRANCH:
            match = bool(self.branch_regex.fullmatch(ref.name))

        if not (ref.remote == self.remote and match):
            return False

        if self._predicate:
            r = self._predicate(root, ref)
            if isawaitable(r):
                r = await r
            if not r:
                return False
        return True

    async def retrieve(self, root: Path) -> Iterable[GitRef]:
        """
        List all build targets.

        This retrieves all references from git and filters them using the
        options this instance was initialized with.

        Parameters
        ----------
        root : Path
            The root path of the project.

        Returns
        -------
        tuple[GitRef]
            The revisions/git references to build.

        """

        async def handle(ref: GitRef) -> GitRef | None:
            if await self.predicate(root, ref):
                return ref
            return None

        tasks = []
        async for ref in _get_all_refs(root):
            tasks.append(handle(ref))

        return tuple(filter(None, await asyncio.gather(*tasks)))
