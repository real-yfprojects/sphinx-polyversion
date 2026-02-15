"""Git VCS support."""

from __future__ import annotations

import asyncio
import enum
import re
import shutil
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
)

from sphinx_polyversion.json import GLOBAL_DECODER
from sphinx_polyversion.utils import async_all
from sphinx_polyversion.vcs import VersionProvider

__all__ = ["Git", "GitRef", "GitRefType", "file_predicate", "refs_by_type"]

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
    return asyncio.run(_resolve_ref(repo, "HEAD"))


async def _resolve_ref(repo: Path, ref: str) -> str:
    """
    Resolve a git ref to its commit hash.

    Parameters
    ----------
    repo : Path
        The git repository.
    ref : str
        The ref to resolve.

    Returns
    -------
    str
        The hex obj hash of the commit.

    Raises
    ------
    CalledProcessError
        The git process exited with an error.

    """
    cmd = (
        "git",
        "rev-parse",
        f"{ref}^{{commit}}",
    )
    process = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, cwd=repo)
    out, err = await process.communicate()
    if process.returncode:
        raise CalledProcessError(process.returncode, " ".join(cmd), stderr=err)
    return out.decode().rstrip("\n")


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


async def _init_submodules(repo: Path) -> None:
    """
    Initialize git submodules in the given repo.

    Parameters
    ----------
    repo : Path
        The git repository.

    Raises
    ------
    CalledProcessError
        The git process exited with an error.

    """
    logger.debug("Initializing git submodules in %s", repo)
    cmd = ("git", "submodule", "init")
    process = await asyncio.create_subprocess_exec(*cmd, cwd=repo, stderr=PIPE)
    out, err = await process.communicate()
    if process.returncode:
        raise CalledProcessError(process.returncode, " ".join(cmd), stderr=err)


async def _fetch_ref(repo: Path, ref: str) -> None:
    """
    Fetch a ref from origin if it is not available locally.

    Parameters
    ----------
    repo : Path
        The git repository.
    ref : str
        The ref to fetch.

    """
    # check whether commit is present locally
    cmd: tuple[str, ...] = ("git", "rev-parse", "--verify", ref)
    process = await asyncio.create_subprocess_exec(*cmd, cwd=repo)
    _ = await process.communicate()

    # download ref if not present locally
    if process.returncode:
        logger.debug("Local ref not found, fetching from remote")
        cmd = ("git", "fetch", "--no-tags", "origin", ref)
        process = await asyncio.create_subprocess_exec(*cmd, cwd=repo, stderr=PIPE)
        out, err = await process.communicate()
        if process.returncode:
            raise CalledProcessError(process.returncode, " ".join(cmd), stderr=err)


async def _copy_tree(
    repo: Path, ref: str, dest: str | Path, buffer_size: int = 0
) -> None:
    """
    Copy the contents of a ref into a location in the file system.

    ..warning::
        This doesn't recurse into git submodules.
        Use :func:`_copy_tree_rec` for that.

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
    logger.debug("Retrieving contents of ref %s in %s", ref, repo)
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


async def _copy_tree_rec(
    repo: Path, ref: str, dest: str | Path, buffer_size: int = 0, fetch: bool = False
) -> None:
    """
    Copy the contents of a ref into a location in the file system.

    Recurse into git submodules. If a submodule ref is not available locally,
    it will be fetched from the remote `origin`.

    ..sealso::
        :func:`_copy_tree` for a non-recursive version
        that doesn't handle submodules.

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
    fetch : bool
        Whether to fetch the ref from origin if it is not available locally.
        This is used by recursive calls for submodules. Defaults to False.

    Raises
    ------
    CalledProcessError
        The git process exited with an error.

    """
    if fetch:
        await _fetch_ref(repo, ref)

    # ensure submodules are initialized
    await _init_submodules(repo)

    # retrieve git submodules entry points and refs
    # Use default ls-tree output to maintain compatibility with older git versions.
    # Default entry format per NUL-delimited line:
    #   <mode> <type> <object>\t<path>[]
    # For submodules: mode=160000, type=commit, object=<commit-sha>
    # TODO: support file lists larger than buffer_size by using a temporary file for output
    cmd = (
        "git",
        "ls-tree",
        "-r",
        "-z",
        ref,
    )
    process = await asyncio.create_subprocess_exec(
        *cmd, cwd=repo, stdout=PIPE, stderr=PIPE
    )
    out, err = await process.communicate()
    if process.returncode:
        raise CalledProcessError(process.returncode, " ".join(cmd), stderr=err)
    lines = out.decode().split("\0")
    submodules = {}
    for line in lines:
        if not line.strip():
            continue
        meta, path = line.strip().split("\t", 1)
        parts = meta.strip().split()
        # Expect: mode type object
        if len(parts) < 3:  # noqa: PLR2004
            logger.warning("Unexpected ls-tree entry: %s", line)
            continue
        mode, _type, obj = parts[0], parts[1], parts[2]
        if mode == "160000":  # gitlink -> submodule
            submodules[Path(path)] = obj

    # retrieve commit contents of root repo as a tar archive
    await _copy_tree(repo, ref, dest, buffer_size)

    # recursive call into each submodule but allow fetching from remote repos
    for submodule, sub_ref in submodules.items():
        sub_repo = repo / submodule
        if not sub_repo.exists():
            logger.warning("Submodule %s not initialized in repo %s", submodule, repo)
            continue
        # verify submodule folder is a standalone git repo; if not, skip gracefully
        if not (sub_repo / ".git").exists():
            logger.warning(
                "Submodule %s not a standalone git repository in %s; skipping",
                submodule,
                repo,
            )
            continue
        sub_dest = Path(dest) / submodule
        sub_dest.mkdir(parents=True, exist_ok=True)
        await _copy_tree_rec(
            sub_repo, sub_ref, sub_dest, buffer_size=buffer_size, fetch=True
        )


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


async def _get_unignored_files(repo: Path) -> AsyncGenerator[Path, None]:
    """
    List all unignored files in the directory.

    This uses git to retrieve all tracked and untracked files but excludes
    files ignored e.g. by `.gitignore`.

    Parameters
    ----------
    repo : Path
        The git repository.

    Raises
    ------
    CalledProcessError
        The git process exited with an error.

    Returns
    -------
    AsyncGenerator[Path, None]
        The paths to all un-ignored files in the directory (recursive)

    """
    # ensure submodules are initialized
    await _init_submodules(repo)

    # list tracked files
    cmd = (
        "git",
        "ls-files",
        "--stage",
        "--cached",
    )
    # output has format <mode> <obj> <stage>\t<path>
    process = await asyncio.create_subprocess_exec(*cmd, cwd=repo, stdout=PIPE)
    while line := await process.stdout.readline():  # type: ignore[union-attr]
        meta, path_str = line.strip().decode().split("\t", 1)
        mode, _ = meta.strip().split(" ", 1)
        path = Path(path_str.strip())
        if mode == "160000":  # gitlink -> submodule
            # recursively list files in submodule if it exists/initialized
            sub_path = repo / path
            if not sub_path.exists():
                logger.warning("Submodule %s not initialized in repo %s", path, repo)
                continue
            async for sub_file in _get_unignored_files(sub_path):
                yield path / sub_file
        else:
            yield path
    await process.wait()
    if process.returncode:
        raise CalledProcessError(process.returncode, " ".join(cmd))

    # lits untracked and un-ignored files
    cmd = (
        "git",
        "ls-files",
        "--others",
        "--exclude-standard",
    )
    process = await asyncio.create_subprocess_exec(*cmd, cwd=repo, stdout=PIPE)
    while line := await process.stdout.readline():  # type: ignore[union-attr]
        path_str = line.strip().decode()
        yield Path(path_str)
    await process.wait()
    if process.returncode:
        raise CalledProcessError(process.returncode, " ".join(cmd))


# -- VersionProvider API -----------------------------------------------------


async def closest_tag(root: Path, ref: GitRef, tags: tuple[str]) -> str | None:
    """
    Find the closest ancestor of a given ref from a list of tags.

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
    # determine commit hashes for each tag
    hash_to_tag = {await _resolve_ref(root, tag): tag for tag in tags}

    # iterate over ancestors until one is in `tags`
    cmd = (
        "git",
        "rev-list",
        "--full-history",
        "--sparse",
        ref.obj,
    )
    process = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, cwd=root)
    while h := await process.stdout.readline():  # type: ignore[union-attr]
        h = h.strip().decode()
        if h in hash_to_tag:
            process.terminate()
            await process.wait()
            return hash_to_tag[h]

    await process.wait()
    if process.returncode:
        raise CalledProcessError(process.returncode, " ".join(cmd))
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
        await _copy_tree_rec(root, revision.obj, dest, self.buffer_size)

    async def checkout_local(self, root: Path, dest: Path) -> None:
        """
        Create copy of the local working directory at the given path.

        This doesn't copy files ignored by `git` if possible.
        Otherwise all files are copied as a fallback.

        Parameters
        ----------
        root : Path
            The root path of the project.
        dest : Path
            The destination to extract the revision to.

        """
        try:
            async for file in _get_unignored_files(root):
                source = root / file
                target = dest / file
                target.parent.mkdir(parents=True, exist_ok=True)
                assert source.exists()
                shutil.copy2(source, target, follow_symlinks=False)
        except CalledProcessError:
            logger.warning(
                "Could not list un-ignored files using git. Copying full working directory..."
            )
            shutil.copytree(root, dest, symlinks=True, dirs_exist_ok=True)

    async def predicate(self, root: Path, ref: GitRef) -> bool:
        """
        Check whether a revision should be build.

        This predicate is used by :meth:`retrieve` to filter the
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
