"""Setuptools SCM integration for sphinx-polyversion."""

from __future__ import annotations

import dataclasses
import shlex
from logging import getLogger
from pathlib import Path
from typing import Tuple, TypeVar

from packaging.utils import canonicalize_name
from setuptools_scm import Configuration, _get_version
from setuptools_scm.git import DEFAULT_DESCRIBE

from sphinx_polyversion.driver import DefaultDriver
from sphinx_polyversion.git import GitRef
from sphinx_polyversion.pyvenv import VirtualPythonEnvironment
from sphinx_polyversion.utils import to_thread

logger = getLogger(__name__)


async def version_for_ref(repo_path: str | Path, ref: str) -> Tuple[str, str] | None:
    """
    Get version that `setuptools_scm` determined for a given revision.

    Calls `setuptools-scm` using the configuration in the `pyproject.toml`
    file. Alters the git describe command configured by appending
    the given :paramref:`ref`.

    .. warning::

        Only works when using git vcs.

    .. warning::

        Doesn't work for legacy python projects that do not use a `pyproject.toml`
        file.


    Parameters
    ----------
    repo_path : str | Path
        The location of the git repository.
    ref : str
        The reference of the revision.

    Returns
    -------
    Tuple[str, str] | None
        The version determined by `setuptools-scm`
        and the canonical distribution name, optional

    Raises
    ------
    FileNotFoundError
        No `pyproject.toml` file was found in the repo.

    """
    # Load project config for `setuptools-scm`
    repo_path = Path(repo_path)
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError(f"Could not find configuration file {pyproject}")
    config = Configuration.from_file(pyproject)

    # determine distribution name
    if not config.dist_name:
        raise ValueError(
            f"Could not determine distribution name from {pyproject}, "
            "please add a [project] section with a name field"
        )
    dist_name = canonicalize_name(config.dist_name)

    # Alter `git describe` command to use the ref
    cmd = config.scm.git.describe_command
    if cmd is None:
        # Use the `setuptools-scm`'s default describe command
        cmd = list(DEFAULT_DESCRIBE)
    elif isinstance(cmd, str):
        cmd = shlex.split(cmd)
    cmd = list(cmd)
    cmd.append(ref)

    # remove "--dirty" if present
    # its incompatible with describing a specific ref
    if "--dirty" in cmd:
        cmd.remove("--dirty")

    # Update configuration
    git_cfg = dataclasses.replace(config.scm.git, describe_command=cmd)
    scm_cfg = dataclasses.replace(config.scm, git=git_cfg)
    config = dataclasses.replace(config, scm=scm_cfg)

    # Get the version (don't write any version files).
    version = await to_thread(_get_version, config, force_write_version_files=False)
    if not version:
        return None
    return (version, dist_name)


RT = TypeVar("RT", bound=GitRef)
ENV = TypeVar("ENV", bound=VirtualPythonEnvironment)
S = TypeVar("S")


class SetuptoolsScmDriver(DefaultDriver[RT, ENV, S]):
    """
    Driver that uses `setuptools-scm` to determine the version of each revision.

    This driver requires that the project uses `setuptools-scm` and has a
    `pyproject.toml` file in the root of the repository.

    .. note::

        Must be used with
        :class:`~sphinx_polyversion.git.GitRef` (thus git vcs)
        and subclasses of :class:`~sphinx_polyversion.pyvenv.VirtualPythonEnvironment`

    .. note::

        Doesn't work for legacy python projects that do not use a `pyproject.toml`
        file.

    Parameters
    ----------
    cwd : Path
        The current working directory
    output_dir : Path
        The directory where to place the built docs.
    vcs : VersionProvider[RT]
        The version provider to use.
    builder : Builder[ENV, Any]
        The builder to use.
    env : Callable[[Path, str], ENV]
        A factory producing the environments to use.
    data_factory : Callable[[DefaultDriver[RT, ENV, S], RT, ENV], JSONable], optional
        A callable returning the data to pass to the builder.
    root_data_factory : Callable[[DefaultDriver[RT, ENV, S]], dict[str, Any]], optional
        A callable returning the variables to pass to the jinja templates.
    namer : Callable[[RT], str], optional
        A callable determining the name of a revision.
    selector: Callable[[RT, Iterable[S]], S | Coroutine[Any, Any, S]], optional
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

    async def init_environment(self, path: Path, rev: RT) -> ENV:
        """
        Initialize the build environment for a revision and path.

        The environment will be used to build the given revision and
        the path specifies the location where the revision is checked out.

        This implementation calls `setuptools-scm` to determine the version
        for the given revision and sets the environment variable
        `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_<DIST_NAME>` in the returned
        environment.

        Parameters
        ----------
        path : Path
            The location of the revisions files.
        rev : GitRef
            The revision the environment is used for.

        Returns
        -------
        VirtualPythonEnvironment

        """
        f = await super().init_environment(path, rev)

        logger.info("Calling setuptools-scm to determine version for %s", rev.name)
        try:
            r = await version_for_ref(self.root, rev.obj)
        except FileNotFoundError:
            logger.warning(
                "Could not find pyproject.toml file in %s, "
                "skipping setuptools-scm integration",
                self.root,
            )
            r = None

        if r is None:
            logger.warning(
                "Couldn't determine `setuptools-scm` version for %s", rev.name
            )
            return f

        version, dist_name = r
        var_dist_name = dist_name.replace("-", "_").upper()

        f.env.setdefault(f"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_{var_dist_name}", version)
        return f
