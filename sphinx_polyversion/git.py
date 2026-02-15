"""Git VCS support."""

from __future__ import annotations

import asyncio
import enum
import re
import shutil
import tempfile
import uuid
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


regex_ref = r"refs/(?P<type>remotes/(?P<remote>[^/]+)|\w+)/(?P<name>\S+)"
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
    Initialize and update git submodules in the given repo.

    This clones missing submodule repositories and checks out the commit
    pinned by the current HEAD. Failures are logged but not raised, since
    individual submodules may be unreachable while others succeed.

    Parameters
    ----------
    repo : Path
        The git repository.

    """
    logger.info("Initializing git submodules in %s", repo)
    cmd = ("git", "submodule", "update", "--init", "--recursive")
    process = await asyncio.create_subprocess_exec(
        *cmd, cwd=repo, stdout=DEVNULL, stderr=PIPE
    )
    _, err = await process.communicate()
    if process.returncode:
        logger.warning(
            "git submodule update --init failed in %s (rc=%d): %s",
            repo,
            process.returncode,
            err.decode().strip() if err else "",
        )


async def _copy_tree(repo: Path, ref: str, dest: str | Path) -> None:
    """
    Copy the contents of a ref into a location in the file system.

    Creates a temporary git worktree at the target ref and uses
    ``git submodule update --init --recursive`` to let Git resolve
    submodule URLs (including relative ones) natively.

    Parameters
    ----------
    repo : Path
        The repo of the ref
    ref : str
        The ref
    dest : Union[str, Path]
        The destination to copy the contents to

    Raises
    ------
    CalledProcessError
        The git process exited with an error.

    """
    with tempfile.TemporaryDirectory() as tmp:
        wt_path = Path(tmp) / f"wt-{uuid.uuid4().hex}"

        # Create a detached worktree at the target ref
        cmd: tuple[str, ...] = (
            "git",
            "worktree",
            "add",
            "--detach",
            str(wt_path),
            ref,
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=repo, stdout=DEVNULL, stderr=PIPE
        )
        _, err = await proc.communicate()
        if proc.returncode:
            raise CalledProcessError(proc.returncode, " ".join(cmd), stderr=err)

        try:
            # Let git initialize all submodules recursively
            # (handles relative URLs via the superproject remote)
            cmd = ("git", "submodule", "update", "--init", "--recursive")
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=wt_path, stdout=DEVNULL, stderr=PIPE
            )
            _, err = await proc.communicate()
            if proc.returncode:
                logger.warning(
                    "git submodule update --init --recursive failed: %s",
                    err.decode().strip() if err else "",
                )

            # Copy worktree contents to dest, excluding .git dirs
            shutil.copytree(
                wt_path,
                dest,
                ignore=shutil.ignore_patterns(".git"),
                dirs_exist_ok=True,
                symlinks=True,
            )
        finally:
            rm_cmd = ("git", "worktree", "remove", "--force", str(wt_path))
            proc = await asyncio.create_subprocess_exec(
                *rm_cmd, cwd=repo, stdout=DEVNULL, stderr=DEVNULL
            )
            await proc.communicate()


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


async def _collect_ignored_for(root: Path) -> set[Path]:
    """
    Collect git-ignored paths for a single repository root.

    Parameters
    ----------
    root : Path
        The git repository or submodule root.

    Returns
    -------
    set[Path]
        Absolute paths of ignored files and directories.

    """
    cmd = (
        "git",
        "ls-files",
        "-z",
        "--ignored",
        "--exclude-standard",
        "--others",
        "--directory",
        "--no-empty-directory",
    )
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=root,
        stdout=PIPE,
        stderr=PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode:
        raise CalledProcessError(proc.returncode, " ".join(cmd), stderr=err)
    ignored: set[Path] = set()
    if out:
        for entry in out.decode().split("\0"):
            if entry:
                ignored.add(root / entry.rstrip("/"))
    return ignored


async def _get_submodule_paths(repo: Path) -> list[Path]:
    """
    Return paths of initialized submodules (recursive).

    Parameters
    ----------
    repo : Path
        The git repository.

    Returns
    -------
    list[Path]
        Absolute paths of initialized submodule directories.

    """
    cmd = ("git", "submodule", "status", "--recursive")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=repo,
        stdout=PIPE,
        stderr=DEVNULL,
    )
    out, err = await proc.communicate()
    if proc.returncode:
        raise CalledProcessError(proc.returncode, " ".join(cmd), stderr=err)
    paths: list[Path] = []
    if out:
        for line in out.decode().splitlines():
            # format: " <sha> <path> (<desc>)" or "-<sha> <path>" (not init'd)
            parts = line.strip().split()
            if len(parts) >= 2 and not parts[0].startswith("-"):  # noqa: PLR2004
                sub_path = repo / parts[1]
                if sub_path.is_dir():
                    paths.append(sub_path)
    return paths


async def _collect_ignored(repo: Path) -> set[Path]:
    """
    Pre-compute all git-ignored paths for a repo and its submodules.

    Returns absolute paths.  Directories are included (without trailing
    slash) so that :func:`_make_copytree_filter` can prune them early.

    Parameters
    ----------
    repo : Path
        The git repository.

    Returns
    -------
    set[Path]
        Absolute paths of ignored files and directories.

    """
    ignored = await _collect_ignored_for(repo)
    for sub_path in await _get_submodule_paths(repo):
        ignored.update(await _collect_ignored_for(sub_path))

    return ignored


def _make_copytree_filter(
    ignored: set[Path],
) -> Callable[[str, list[str]], set[str]]:
    """
    Return an ignore callback for :func:`shutil.copytree`.

    Parameters
    ----------
    ignored : set[Path]
        Absolute paths of files/directories to skip.

    Returns
    -------
    Callable[[str, list[str]], set[str]]
        An ignore function suitable for ``shutil.copytree(ignore=...)``.

    """

    def ignore(directory: str, entries: list[str]) -> set[str]:
        dir_path = Path(directory)
        return {e for e in entries if e == ".git" or dir_path / e in ignored}

    return ignore


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
    ) -> None:
        """Init."""
        super().__init__()
        self.remote = remote

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
        await _copy_tree(root, revision.obj, dest)

    async def checkout_local(self, root: Path, dest: Path) -> None:
        """
        Create copy of the local working directory at the given path.

        This doesn't copy files ignored by `git` if possible.
        Otherwise all files are copied as a fallback.

        .. warning::
            This may alter the user's working tree
            by calling ``git submodule update --init``.

        Parameters
        ----------
        root : Path
            The root path of the project.
        dest : Path
            The destination to extract the revision to.

        """
        await _init_submodules(root)
        try:
            ignored = await _collect_ignored(root)
        except CalledProcessError:
            logger.warning(
                "Could not determine ignored files using git. "
                "Copying full working directory..."
            )
            shutil.copytree(root, dest, symlinks=True, dirs_exist_ok=True)
            return
        shutil.copytree(
            root,
            dest,
            ignore=_make_copytree_filter(ignored),
            symlinks=True,
            dirs_exist_ok=True,
        )

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
