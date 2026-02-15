"""Test the `Git` class."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Mapping, NamedTuple, Tuple

import pytest
import pytest_asyncio

from sphinx_polyversion.git import (
    Git,
    GitRef,
    GitRefType,
    _parse_ref,
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


@pytest_asyncio.fixture
async def git_testrepo(tmp_path: Path) -> Tuple[Path, List[GitRef]]:
    """Create a git repository for testing."""
    env = no_git_env()

    async def run_git(*args: str, capture: bool = False) -> str:
        cmd = ("git", *NO_FS_MONITOR, *args)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
        )
        out, err = await process.communicate()
        if process.returncode:
            raise subprocess.CalledProcessError(
                process.returncode, " ".join(cmd), stderr=err
            )
        return out.decode() if out else ""

    # init repo
    await run_git("init")
    await run_git("config", "user.email", "example@example.com")
    await run_git("config", "user.name", "example")
    await run_git("config", "commit.gpgsign", "false")
    await run_git("config", "init.defaultBranch", "main")

    # create some files and directories to commit
    tmp_path.joinpath("test.txt").write_text("test")
    tmp_path.joinpath("dir1").mkdir()
    tmp_path.joinpath("dir2").mkdir()
    tmp_path.joinpath("dir1", "file1.txt").write_text("file1")
    tmp_path.joinpath("dir2", "file3.txt").write_text("file3")

    await run_git("add", ".")
    await run_git("commit", "-m", "test")

    # create a branch
    await run_git("branch", "dev")

    # create changes to commit
    tmp_path.joinpath("test.txt").write_text("test2")
    tmp_path.joinpath("dir1", "file2.txt").write_text("file2")
    tmp_path.joinpath("dir1", "file1.txt").write_text("file1a")
    tmp_path.joinpath("dir2", "file3.txt").write_text("file3a")

    await run_git("add", ".")
    await run_git("commit", "-m", "test2")

    # create a tag
    await run_git("tag", "1.0", "-m", "")

    # commit some more changes
    tmp_path.joinpath("test.txt").write_text("test3")
    tmp_path.joinpath("dir1", "file2.txt").write_text("file2a")
    tmp_path.joinpath("dir1", "file1.txt").write_text("file1b")

    await run_git("add", ".")
    await run_git("commit", "-m", "test3")

    # create another branch
    await run_git("branch", "feature")

    # tag the latest commit
    await run_git("tag", "2.0", "-m", "")

    p_out = await run_git(
        "for-each-ref", "--format=%(objectname) %(refname)", capture=True
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
    lines = [line.split() for line in p_out.splitlines()]
    refs = [
        GitRef(r.split("/")[-1], h, r, t, d)
        for t, (h, r), d in zip(types, lines, dates)
    ]
    return tmp_path, refs


@pytest.fixture
def git() -> Git:
    """Create a `Git` instance for testing."""
    return Git(branch_regex=".*", tag_regex=".*")


@pytest.fixture
def git_with_predicate() -> Git:
    """Create a `Git` instance with a predicate for testing."""

    async def predicate(root: Path, ref: GitRef) -> bool:
        return ref.name in ["test", "feature", "1.0"]

    return Git(
        branch_regex=".*",
        tag_regex=".*",
        predicate=predicate,
    )


@pytest.mark.asyncio
async def test_aroot(git: Git, git_testrepo: Tuple[Path, List[GitRef]]):
    """Test the `aroot` method."""
    repo_path, _ = git_testrepo
    root = await git.aroot(repo_path)
    assert root == repo_path

    root = await git.aroot(repo_path / "dir1")
    assert root == repo_path


@pytest.mark.asyncio
async def test_checkout(
    git: Git,
    git_testrepo: Tuple[Path, List[GitRef]],
    tmp_path: Path,
):
    """Test the `checkout` method."""
    repo_path, refs = git_testrepo
    await git.checkout(repo_path, tmp_path, refs[0])
    assert (tmp_path / "test.txt").read_text() == "test"


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_retrieve(git: Git, git_testrepo: Tuple[Path, List[GitRef]]):
    """Test the `retrieve` method."""
    root, git_refs = git_testrepo
    refs = await git.retrieve(root)
    assert len(refs) == 5

    for ref1, ref2 in zip(refs, git_refs):
        assert compare_refs(ref1, ref2)


@pytest.mark.asyncio
async def test_retrieve_with_predicate(
    git_with_predicate: Git, git_testrepo: Tuple[Path, List[GitRef]]
):
    """Test the `retrieve` method with a predicate."""
    root, git_refs = git_testrepo
    refs = await git_with_predicate.retrieve(root)
    assert len(refs) == 2
    assert compare_refs(refs[0], git_refs[1])
    assert compare_refs(refs[1], git_refs[3])


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


def test_parse_remote_ref():
    """Test that `_parse_ref` parses remote branch refs correctly."""
    line = "0123456789abcdef\trefs/remotes/origin/feature\t2023-08-29 19:45:09 +0000"
    ref = _parse_ref(line)
    assert ref is not None
    assert ref.name == "feature"
    assert ref.remote == "origin"
    assert ref.type_ == GitRefType.BRANCH
    assert ref.obj == "0123456789abcdef"
    assert ref.ref == "refs/remotes/origin/feature"


# --- Submodule tests ---------------------------------------------------------


@pytest.fixture(autouse=True)
def _allow_file_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Allow local file:// submodule URLs for all tests in this module.

    ``git submodule update --init --recursive`` spawns nested ``git clone``
    processes that do not inherit the parent repo's config.
    ``GIT_ALLOW_PROTOCOL`` is propagated through all child processes.
    """
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file:https:ssh:git")


async def _run_git(
    cwd: Path,
    *args: str,
    env_add: Mapping[str, str] | None = None,
    capture: bool = False,
) -> str:
    git = ("git", *NO_FS_MONITOR, *args)
    env = no_git_env()
    if env_add:
        env.update(env_add)
    proc = await asyncio.create_subprocess_exec(
        *git,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, " ".join(git), stderr=err)
    return out.decode() if out else ""


class SubmoduleRepo(NamedTuple):
    """Container for the `git_submodule_repo` fixture."""

    main: Path
    make_fetch_needed: Callable[[], Awaitable[None]]


@pytest_asyncio.fixture
async def git_submodule_repo(tmp_path: Path) -> SubmoduleRepo:
    """
    Create a git repository with a submodule and provide a hook to force a fetch-needed state.

    Layout:
      tmp/subrepo            # standalone repo
      tmp/main               # includes subrepo as submodule at third_party/sub

    Initially, main pins submodule at v1; subrepo then advances to v2.
    The returned hook replaces the submodule working tree with a shallow clone
    (v2 only) and recreates staged/untracked files so that checkout requires fetching v1.
    """
    # Create subrepo with initial commit (v1)
    subrepo = tmp_path / "subrepo"
    subrepo.mkdir()
    await _run_git(subrepo, "init")
    await _run_git(subrepo, "config", "user.email", "example@example.com")
    await _run_git(subrepo, "config", "user.name", "example")
    await _run_git(subrepo, "config", "commit.gpgsign", "false")
    (subrepo / "lib.txt").write_text("sub v1")
    (subrepo / "committed1.txt").write_text("c1 v1")
    (subrepo / "committed2.txt").write_text("c2 v1")
    await _run_git(subrepo, "add", ".")
    await _run_git(subrepo, "commit", "-m", "sub v1")

    # Create main with submodule pinned at v1
    mainrepo = tmp_path / "main"
    mainrepo.mkdir()
    await _run_git(mainrepo, "init")
    await _run_git(mainrepo, "config", "user.email", "example@example.com")
    await _run_git(mainrepo, "config", "user.name", "example")
    await _run_git(mainrepo, "config", "commit.gpgsign", "false")
    await _run_git(mainrepo, "config", "protocol.file.allow", "always")
    (mainrepo / "root.txt").write_text("root")
    await _run_git(mainrepo, "add", ".")
    await _run_git(mainrepo, "commit", "-m", "root")

    await _run_git(
        mainrepo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        subrepo.as_posix(),
        "third_party/sub",
        env_add={"GIT_ALLOW_PROTOCOL": "file"},
    )
    await _run_git(mainrepo, "commit", "-m", "add submodule at v1")

    # Advance subrepo to v2 (HEAD)
    (subrepo / "lib.txt").write_text("sub v2")
    await _run_git(subrepo, "add", ".")
    await _run_git(subrepo, "commit", "-m", "sub v2")

    # staged & untracked files in the submodule working copy
    sub_path = mainrepo / "third_party" / "sub"
    (sub_path / "staged1.txt").write_text("s1")
    (sub_path / "staged2.txt").write_text("s2")
    await _run_git(sub_path, "add", "staged1.txt", "staged2.txt")
    (sub_path / "untracked1.txt").write_text("u1")
    (sub_path / "untracked2.txt").write_text("u2")

    async def make_fetch_needed() -> None:
        # Replace submodule working tree with shallow clone that has only v2
        shutil.rmtree(sub_path)
        await _run_git(
            mainrepo,
            "-c",
            "protocol.file.allow=always",
            "clone",
            "--depth=1",
            subrepo.as_posix(),
            "third_party/sub",
            env_add={"GIT_ALLOW_PROTOCOL": "file"},
        )
        await _run_git(sub_path, "config", "protocol.file.allow", "always")
        # recreate staged/untracked in the shallow clone
        (sub_path / "staged1.txt").write_text("s1")
        (sub_path / "staged2.txt").write_text("s2")
        await _run_git(sub_path, "add", "staged1.txt", "staged2.txt")
        (sub_path / "untracked1.txt").write_text("u1")
        (sub_path / "untracked2.txt").write_text("u2")

    return SubmoduleRepo(mainrepo, make_fetch_needed)


@pytest.mark.asyncio
async def test_checkout_with_submodules(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout` should copy pinned submodule contents recursively."""
    mainrepo = git_submodule_repo.main

    # Resolve current HEAD of the main repo to build the GitRef
    head = (await _run_git(mainrepo, "rev-parse", "HEAD", capture=True)).strip()
    ref = GitRef("HEAD", head, "HEAD", GitRefType.BRANCH, datetime.now())

    await git.checkout(mainrepo, tmp_path, ref)

    # Root files should be present
    assert (tmp_path / "root.txt").exists()
    assert (tmp_path / ".gitmodules").exists()

    # Submodule file should be copied at the pinned commit (v1)
    for name, content in (
        ("lib.txt", "sub v1"),
        ("committed1.txt", "c1 v1"),
        ("committed2.txt", "c2 v1"),
    ):
        p = tmp_path / "third_party" / "sub" / name
        assert p.exists()
        assert p.read_text() == content


@pytest.mark.asyncio
async def test_checkout_local_with_submodules(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout_local` should include files from initialized submodules."""
    mainrepo = git_submodule_repo.main

    await git.checkout_local(mainrepo, tmp_path)

    # Submodule working copy in main repo is at v1, ensure it gets copied
    for name, content in (
        ("lib.txt", "sub v1"),
        ("committed1.txt", "c1 v1"),
        ("committed2.txt", "c2 v1"),
    ):
        p = tmp_path / "third_party" / "sub" / name
        assert p.exists()
        assert p.read_text() == content

    # staged files should be copied as they are in the index
    for name in ("staged1.txt", "staged2.txt"):
        p = tmp_path / "third_party" / "sub" / name
        assert p.exists()
        assert p.read_text() in {"s1", "s2"}

    # Untracked files from submodule should also be copied
    for name, content in (("untracked1.txt", "u1"), ("untracked2.txt", "u2")):
        copied_untracked = tmp_path / "third_party" / "sub" / name
        assert copied_untracked.exists()
        assert copied_untracked.read_text() == content


@pytest.mark.asyncio
async def test_checkout_with_submodules_fetch(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout` should fetch missing submodule commits and copy pinned state."""
    mainrepo = git_submodule_repo.main
    await git_submodule_repo.make_fetch_needed()
    head = (await _run_git(mainrepo, "rev-parse", "HEAD", capture=True)).strip()
    ref = GitRef("HEAD", head, "HEAD", GitRefType.BRANCH, datetime.now())

    await git.checkout(mainrepo, tmp_path, ref)

    # Pinned content from v1 should be fetched and used
    for name, content in (
        ("lib.txt", "sub v1"),
        ("committed1.txt", "c1 v1"),
        ("committed2.txt", "c2 v1"),
    ):
        p = tmp_path / "third_party" / "sub" / name
        assert p.exists()
        assert p.read_text() == content


@pytest.mark.asyncio
async def test_checkout_clones_removed_submodule(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout` of an old ref should clone a submodule removed from HEAD."""
    mainrepo = git_submodule_repo.main

    # Record the commit that still has the submodule
    old_head = (await _run_git(mainrepo, "rev-parse", "HEAD", capture=True)).strip()

    # Remove the submodule from HEAD
    await _run_git(mainrepo, "submodule", "deinit", "-f", "--", "third_party/sub")
    await _run_git(mainrepo, "rm", "-f", "third_party/sub")
    shutil.rmtree(mainrepo / ".git" / "modules" / "third_party", ignore_errors=True)
    await _run_git(mainrepo, "commit", "-m", "remove submodule")

    # Checkout the OLD commit that still had the submodule
    ref = GitRef("old", old_head, "old", GitRefType.BRANCH, datetime.now())
    await git.checkout(mainrepo, tmp_path, ref)

    # Root files and submodule content from the old commit should be present
    assert (tmp_path / "root.txt").exists()
    for name, content in (
        ("lib.txt", "sub v1"),
        ("committed1.txt", "c1 v1"),
        ("committed2.txt", "c2 v1"),
    ):
        p = tmp_path / "third_party" / "sub" / name
        assert p.exists()
        assert p.read_text() == content

    # The source repo's working tree must NOT be modified
    assert not (mainrepo / "third_party" / "sub").exists()


@pytest.mark.asyncio
async def test_checkout_recovers_deinitialized_submodule(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout` should re-initialize a deinit'd submodule via `update --init`."""
    mainrepo = git_submodule_repo.main
    with suppress(subprocess.CalledProcessError):
        await _run_git(mainrepo, "submodule", "deinit", "-f", "--", "third_party/sub")

    head = (await _run_git(mainrepo, "rev-parse", "HEAD", capture=True)).strip()
    ref = GitRef("HEAD", head, "HEAD", GitRefType.BRANCH, datetime.now())

    await git.checkout(mainrepo, tmp_path, ref)

    # update --init recovers the submodule; content should be present
    assert (tmp_path / "root.txt").exists()
    for name, content in (
        ("lib.txt", "sub v1"),
        ("committed1.txt", "c1 v1"),
        ("committed2.txt", "c2 v1"),
    ):
        p = tmp_path / "third_party" / "sub" / name
        assert p.exists()
        assert p.read_text() == content


@pytest.mark.asyncio
async def test_checkout_skips_unavailable_submodule(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout` should skip a submodule whose remote is unreachable."""
    mainrepo = git_submodule_repo.main
    # Deinitialize, remove git object store, and remove the remote repo
    # so neither update --init nor clone can recover
    with suppress(subprocess.CalledProcessError):
        await _run_git(mainrepo, "submodule", "deinit", "-f", "--", "third_party/sub")
    shutil.rmtree(mainrepo / ".git" / "modules" / "third_party", ignore_errors=True)
    shutil.rmtree(tmp_path / "subrepo", ignore_errors=True)

    head = (await _run_git(mainrepo, "rev-parse", "HEAD", capture=True)).strip()
    ref = GitRef("HEAD", head, "HEAD", GitRefType.BRANCH, datetime.now())

    await git.checkout(mainrepo, tmp_path, ref)

    # Root files copied, submodule gracefully skipped
    assert (tmp_path / "root.txt").exists()
    for name in ("lib.txt", "committed1.txt", "committed2.txt"):
        assert not (tmp_path / "third_party" / "sub" / name).exists()


@pytest.mark.asyncio
async def test_checkout_local_recovers_deinitialized_submodule(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout_local` should re-initialize a deinit'd submodule."""
    mainrepo = git_submodule_repo.main
    with suppress(subprocess.CalledProcessError):
        await _run_git(mainrepo, "submodule", "deinit", "-f", "--", "third_party/sub")
    shutil.rmtree(mainrepo / "third_party" / "sub", ignore_errors=True)

    await git.checkout_local(mainrepo, tmp_path)

    # update --init recovers the submodule; committed files should be present
    assert (tmp_path / "root.txt").exists()
    for name, content in (
        ("lib.txt", "sub v1"),
        ("committed1.txt", "c1 v1"),
        ("committed2.txt", "c2 v1"),
    ):
        p = tmp_path / "third_party" / "sub" / name
        assert p.exists()
        assert p.read_text() == content


@pytest.mark.asyncio
async def test_checkout_local_skips_unavailable_submodule(
    git: Git, git_submodule_repo: SubmoduleRepo, tmp_path: Path
):
    """`checkout_local` should skip a submodule whose remote is unreachable."""
    mainrepo = git_submodule_repo.main
    with suppress(subprocess.CalledProcessError):
        await _run_git(mainrepo, "submodule", "deinit", "-f", "--", "third_party/sub")
    shutil.rmtree(mainrepo / ".git" / "modules" / "third_party", ignore_errors=True)
    shutil.rmtree(mainrepo / "third_party" / "sub", ignore_errors=True)
    shutil.rmtree(tmp_path / "subrepo", ignore_errors=True)

    await git.checkout_local(mainrepo, tmp_path)

    assert (tmp_path / "root.txt").exists()
    for name in (
        "lib.txt",
        "committed1.txt",
        "committed2.txt",
    ):
        assert not (tmp_path / "third_party" / "sub" / name).exists()


# --- Nested submodule tests --------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_with_nested_submodules(git: Git, tmp_path: Path):
    """`checkout` should recurse into nested submodules (sub within sub)."""

    async def rg(cwd: Path, *args: str, **kwargs: Any) -> str:
        return await _run_git(cwd, *args, **kwargs, capture=True)

    async def rg_void(cwd: Path, *args: str, **kwargs: Any) -> None:
        await _run_git(cwd, *args, **kwargs)

    # Create innermost repo (leaf)
    leaf = tmp_path / "leaf"
    leaf.mkdir()
    await rg_void(leaf, "init")
    await rg_void(leaf, "config", "user.email", "e@e.com")
    await rg_void(leaf, "config", "user.name", "e")
    await rg_void(leaf, "config", "commit.gpgsign", "false")
    (leaf / "leaf.txt").write_text("leaf content")
    await rg_void(leaf, "add", ".")
    await rg_void(leaf, "commit", "-m", "leaf")

    # Create middle repo with leaf as submodule
    middle = tmp_path / "middle"
    middle.mkdir()
    await rg_void(middle, "init")
    await rg_void(middle, "config", "user.email", "e@e.com")
    await rg_void(middle, "config", "user.name", "e")
    await rg_void(middle, "config", "commit.gpgsign", "false")
    await rg_void(middle, "config", "protocol.file.allow", "always")
    (middle / "mid.txt").write_text("mid content")
    await rg_void(middle, "add", ".")
    await rg_void(middle, "commit", "-m", "mid")
    await rg_void(
        middle,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        leaf.as_posix(),
        "deps/leaf",
        env_add={"GIT_ALLOW_PROTOCOL": "file"},
    )
    await rg_void(middle, "commit", "-m", "add leaf submodule")

    # Create outer repo with middle as submodule
    outer = tmp_path / "outer"
    outer.mkdir()
    await rg_void(outer, "init")
    await rg_void(outer, "config", "user.email", "e@e.com")
    await rg_void(outer, "config", "user.name", "e")
    await rg_void(outer, "config", "commit.gpgsign", "false")
    await rg_void(outer, "config", "protocol.file.allow", "always")
    (outer / "root.txt").write_text("outer content")
    await rg_void(outer, "add", ".")
    await rg_void(outer, "commit", "-m", "outer")
    await rg_void(
        outer,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        middle.as_posix(),
        "vendor/mid",
        env_add={"GIT_ALLOW_PROTOCOL": "file"},
    )
    await rg_void(outer, "commit", "-m", "add middle submodule")

    # Pre-initialize the nested leaf submodule inside middle's working copy.
    # In tests, git clone blocks file:// transport unless the spawning repo
    # has protocol.file.allow=always, but `git submodule update --init` spawns
    # a clone subprocess that doesn't inherit the parent's local config.
    # Pre-initializing here avoids this test-only issue.
    mid_in_outer = outer / "vendor" / "mid"
    await rg_void(mid_in_outer, "config", "protocol.file.allow", "always")
    await rg_void(
        mid_in_outer,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "update",
        "--init",
        env_add={"GIT_ALLOW_PROTOCOL": "file"},
    )

    # Checkout into a fresh destination
    dest = tmp_path / "dest"
    dest.mkdir()
    head = (await rg(outer, "rev-parse", "HEAD")).strip()
    ref = GitRef("HEAD", head, "HEAD", GitRefType.BRANCH, datetime.now())

    await git.checkout(outer, dest, ref)

    # Verify all three levels
    assert (dest / "root.txt").read_text() == "outer content"
    assert (dest / "vendor" / "mid" / "mid.txt").read_text() == "mid content"
    assert (
        dest / "vendor" / "mid" / "deps" / "leaf" / "leaf.txt"
    ).read_text() == "leaf content"
