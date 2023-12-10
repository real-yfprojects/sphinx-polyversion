"""Test the `Git` class."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Mapping, Tuple

import pytest

from sphinx_polyversion.git import (
    Git,
    GitRef,
    GitRefType,
    closest_tag,
    file_exists,
    file_predicate,
)

# Fragments of the following git logic are sourced from
# https://github.com/pre-commit/pre-commit/blob/main/pre_commit/git.py
#
# Original Copyright (c) 2014 pre-commit dev team: Anthony Sottile, Ken Struys
# MIT License

# prevents errors on windows
NO_FS_MONITOR = ("-c", "core.useBuiltinFSMonitor=false")
PARTIAL_CLONE = ("-c", "extensions.partialClone=true")


def no_git_env(_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """
    Clear problematic git env vars.

    Git sometimes sets some environment variables that alter its behaviour.
    You can pass `os.environ` to this method and then pass its return value
    to `subprocess.run` as a environment.

    Parameters
    ----------
    _env : Mapping[str, str] | None, optional
        A dictionary of env vars, by default None

    Returns
    -------
    dict[str, str]
        The same dictionary but without the problematic vars
    """
    # Too many bugs dealing with environment variables and GIT:
    # https://github.com/pre-commit/pre-commit/issues/300
    # In git 2.6.3 (maybe others), git exports GIT_WORK_TREE while running
    # pre-commit hooks
    # In git 1.9.1 (maybe others), git exports GIT_DIR and GIT_INDEX_FILE
    # while running pre-commit hooks in submodules.
    # GIT_DIR: Causes git clone to clone wrong thing
    # GIT_INDEX_FILE: Causes 'error invalid object ...' during commit
    _env = _env if _env is not None else os.environ
    return {
        k: v
        for k, v in _env.items()
        if not k.startswith("GIT_")
        or k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
        or k
        in {
            "GIT_EXEC_PATH",
            "GIT_SSH",
            "GIT_SSH_COMMAND",
            "GIT_SSL_CAINFO",
            "GIT_SSL_NO_VERIFY",
            "GIT_CONFIG_COUNT",
            "GIT_HTTP_PROXY_AUTHMETHOD",
            "GIT_ALLOW_PROTOCOL",
            "GIT_ASKPASS",
        }
    }


@pytest.fixture()
def git_testrepo(tmp_path: Path) -> Tuple[Path, List[GitRef]]:
    """Create a git repository for testing."""
    git = ("git", *NO_FS_MONITOR)
    env = no_git_env()

    def run_git(*args: str) -> None:
        subprocess.run(git + args, cwd=tmp_path, env=env)

    # init repo
    run_git("init")
    run_git("config", "user.email", "example@example.com")
    run_git("config", "user.name", "example")
    run_git("config", "commit.gpgsign", "false")
    run_git("config", "init.defaultBranch", "main")

    # create some files and directories to commit
    tmp_path.joinpath("test.txt").write_text("test")
    tmp_path.joinpath("dir1").mkdir()
    tmp_path.joinpath("dir2").mkdir()
    tmp_path.joinpath("dir1", "file1.txt").write_text("file1")
    tmp_path.joinpath("dir2", "file3.txt").write_text("file3")

    run_git("add", ".")
    run_git("commit", "-m", "test")

    # create a branch
    run_git("branch", "dev")

    # create changes to commit
    tmp_path.joinpath("test.txt").write_text("test2")
    tmp_path.joinpath("dir1", "file2.txt").write_text("file2")
    tmp_path.joinpath("dir1", "file1.txt").write_text("file1a")
    tmp_path.joinpath("dir2", "file3.txt").write_text("file3a")

    run_git("add", ".")
    run_git("commit", "-m", "test2")

    # create a tag
    run_git("tag", "1.0", "-m", "")

    # commit some more changes
    tmp_path.joinpath("test.txt").write_text("test3")
    tmp_path.joinpath("dir1", "file2.txt").write_text("file2a")
    tmp_path.joinpath("dir1", "file1.txt").write_text("file1b")

    run_git("add", ".")
    run_git("commit", "-m", "test3")

    # create another branch
    run_git("branch", "feature")

    # tag the latest commit
    run_git("tag", "2.0", "-m", "")

    p = subprocess.run(
        ["git", "for-each-ref", "--format=%(objectname) %(refname)"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
    )

    types = [
        GitRefType.BRANCH,
        GitRefType.BRANCH,
        GitRefType.BRANCH,
        GitRefType.TAG,
        GitRefType.TAG,
    ]
    dates = [
        datetime(2023, 8, 17, 17, 16, 34),
        datetime(2023, 8, 26, 19, 45, 9),
        datetime(2023, 8, 29, 19, 45, 9),
        datetime(2023, 6, 29, 11, 43, 11),
        datetime(2023, 8, 29, 19, 45, 9),
    ]
    lines = [line.split() for line in p.stdout.decode().splitlines()]
    refs = [
        GitRef(r.split("/")[-1], h, r, t, d)
        for t, (h, r), d in zip(types, lines, dates)
    ]
    return tmp_path, refs


@pytest.fixture()
def git() -> Git:
    """Create a `Git` instance for testing."""
    return Git(branch_regex=".*", tag_regex=".*")


@pytest.fixture()
def git_with_predicate() -> Git:
    """Create a `Git` instance with a predicate for testing."""

    async def predicate(root: Path, ref: GitRef) -> bool:
        return ref.name in ["test", "feature", "1.0"]

    return Git(
        branch_regex=".*",
        tag_regex=".*",
        predicate=predicate,
    )


@pytest.fixture()
def git_with_buffer_size() -> Git:
    """Create a `Git` instance with a buffer size for testing."""
    return Git(branch_regex=".*", tag_regex=".*", buffer_size=1024)


@pytest.mark.asyncio()
async def test_aroot(git: Git, git_testrepo: Tuple[Path, List[GitRef]]):
    """Test the `aroot` method."""
    repo_path, _ = git_testrepo
    root = await git.aroot(repo_path)
    assert root == repo_path

    root = await git.aroot(repo_path / "dir1")
    assert root == repo_path


@pytest.mark.asyncio()
async def test_checkout(
    git: Git,
    git_testrepo: Tuple[Path, List[GitRef]],
    tmp_path: Path,
):
    """Test the `checkout` method."""
    repo_path, refs = git_testrepo
    await git.checkout(repo_path, tmp_path, refs[0])
    assert (tmp_path / "test.txt").read_text() == "test"


@pytest.mark.asyncio()
async def test_checkout_with_buffer(
    git_with_buffer_size: Git,
    git_testrepo: Tuple[Path, List[GitRef]],
    tmp_path: Path,
):
    """Test the `checkout` method."""
    repo_path, refs = git_testrepo
    await git_with_buffer_size.checkout(repo_path, tmp_path, refs[0])
    assert (tmp_path / "test.txt").read_text() == "test"


@pytest.mark.asyncio()
async def test_predicate(git_with_predicate: Git):
    """Test the `predicate` method."""
    root = "."
    assert await git_with_predicate.predicate(root, GitRef("test", "", "", None, None))
    assert not await git_with_predicate.predicate(
        root, GitRef("test2", "", "", None, None)
    )


def compare_refs(ref1: GitRef, ref2: GitRef) -> bool:
    """
    Determine euqality of two `GitRef` instances.

    This is used with `assert` later on.
    """
    # do not compare data since the expected value is not known
    return (
        ref1.name == ref2.name
        and ref1.obj == ref2.obj
        and ref1.ref == ref2.ref
        and ref1.type_ == ref2.type_
    )


@pytest.mark.asyncio()
async def test_retrieve(git: Git, git_testrepo: Tuple[Path, List[GitRef]]):
    """Test the `retrieve` method."""
    root, git_refs = git_testrepo
    refs = await git.retrieve(root)
    assert len(refs) == 5

    for ref1, ref2 in zip(refs, git_refs):
        assert compare_refs(ref1, ref2)


@pytest.mark.asyncio()
async def test_retrieve_with_predicate(
    git_with_predicate: Git, git_testrepo: Tuple[Path, List[GitRef]]
):
    """Test the `retrieve` method with a predicate."""
    root, git_refs = git_testrepo
    refs = await git_with_predicate.retrieve(root)
    assert len(refs) == 2
    assert compare_refs(refs[0], git_refs[1])
    assert compare_refs(refs[1], git_refs[3])


@pytest.mark.asyncio()
async def test_closest_tag(git_testrepo: Tuple[Path, List[GitRef]]):
    """Test the `closest_tag` method."""
    root, git_refs = git_testrepo
    # main branch
    assert (
        await closest_tag(root, git_refs[2], [git_refs[0].obj, "1.0", "2.0"]) == "2.0"
    )
    # 1.0 tag should map to HEAD of dev branch
    assert (
        await closest_tag(root, git_refs[3], [git_refs[0].obj, "2.0"])
        == git_refs[0].obj
    )
    # 1.0 tag should map to itself
    assert (
        await closest_tag(root, git_refs[3], [git_refs[0].obj, "1.0", "2.0"]) == "1.0"
    )
    # 2.0 tag should map to itself
    assert (
        await closest_tag(root, git_refs[4], [git_refs[0].obj, "1.0", "2.0"]) == "2.0"
    )
    # if their is no ancestor None should be returned
    assert await closest_tag(root, git_refs[0], ["1.0", "2.0"]) is None


@pytest.mark.asyncio()
async def test_file_exists(git_testrepo: Tuple[Path, List[GitRef]]):
    """Test the `file_exists` method."""
    root, git_refs = git_testrepo

    # dev branch
    assert await file_exists(root, git_refs[0], Path("test.txt"))
    assert await file_exists(root, git_refs[0], Path("dir1"))
    assert await file_exists(root, git_refs[0], Path("dir2/file3.txt"))
    assert not await file_exists(root, git_refs[0], Path("dir1/file2.txt"))
    # future branch
    assert await file_exists(root, git_refs[1], Path("test.txt"))
    assert await file_exists(root, git_refs[1], Path("dir2"))
    assert await file_exists(root, git_refs[1], Path("dir1/file2.txt"))
    assert not await file_exists(root, git_refs[1], Path("dir3"))


@pytest.mark.asyncio()
async def test_file_predicate(git_testrepo: Tuple[Path, List[GitRef]]):
    """Test the `file_exists` method."""
    root, git_refs = git_testrepo
    git = Git(
        branch_regex=".*",
        tag_regex=".*",
        predicate=file_predicate([Path("dir1/file2.txt"), Path("dir2")]),
    )

    refs = await git.retrieve(root)
    assert len(refs) == 4
    for i in range(4):
        assert compare_refs(refs[i], git_refs[i + 1])
