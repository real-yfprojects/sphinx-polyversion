"""Builder Implementations for running sphinx."""

from __future__ import annotations

import enum
import os
from logging import getLogger
from pathlib import Path, PurePath
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Any, Iterable

from sphinx_polyversion.builder import Builder, BuildError
from sphinx_polyversion.environment import Environment
from sphinx_polyversion.json import GLOBAL_ENCODER, JSONable

if TYPE_CHECKING:
    import json

logger = getLogger(__name__)


class Placeholder(enum.Enum):
    """Placeholders that can be used in commands."""

    #: represents the location of the source files to render the docs from
    SOURCE_DIR = enum.auto()
    #: represents the output location to render the docs to
    OUTPUT_DIR = enum.auto()


class CommandBuilder(Builder[Environment, None]):
    """
    A builder that starts another process.

    This allows you to run any command for building your docs.
    You can use the placeholders from the :class:`Placeholder` enum in the
    command provided. These placeholders will be replaced with their actual
    values before the subprocess is run.

    Parameters
    ----------
    source : PurePath
        The relative source location to pass to the command.
    cmd : Iterable[str  |  Placeholder]
        The command to run.
    encoder : json.JSONEncoder | None, optional
        The encoder to use for serializing the metadata, by default None
    pre_cmd : Iterable[str | Placeholder], optional
        Additional command to run before `cmd`.
    post_cmd : Iterable[str | Placeholder], optional
        Additional command to run after `cmd`.

    """

    def __init__(
        self,
        source: str | PurePath,
        cmd: Iterable[str | Placeholder],
        encoder: json.JSONEncoder | None = None,
        pre_cmd: Iterable[str | Placeholder] | None = None,
        post_cmd: Iterable[str | Placeholder] | None = None,
    ) -> None:
        """
        Init the builder.

        Parameters
        ----------
        source : PurePath
            The relative source location to pass to the command.
        cmd : Iterable[str  |  Placeholder]
            The command to run.
        encoder : json.JSONEncoder | None, optional
            The encoder to use for serializing the metadata, by default None
        pre_cmd : Iterable[str | Placeholder], optional
            Additional command to run before `cmd`.
        post_cmd : Iterable[str | Placeholder], optional
            Additional command to run after `cmd`.

        """
        super().__init__()
        self.cmd = cmd
        self.source = PurePath(source)
        self.logger = logger
        self.encoder = encoder or GLOBAL_ENCODER
        self.pre_cmd = pre_cmd
        self.post_cmd = post_cmd

    async def build(
        self, environment: Environment, output_dir: Path, data: JSONable
    ) -> None:
        """
        Build and render a documentation.

        This method runs the command the instance was created with.
        The metadata will be passed to the subprocess encoded as json
        using the `POLYVERSION_DATA` environment variable.

        Parameters
        ----------
        environment : Environment
            The environment to use for building.
        output_dir : Path
            The output directory to build to.
        data : JSONable
            The metadata to use for building.

        """
        self.logger.info("Building...")
        source_dir = str(environment.path.absolute() / self.source)

        def replace(v: Any) -> str:
            if v == Placeholder.OUTPUT_DIR:
                return str(output_dir)
            if v == Placeholder.SOURCE_DIR:
                return source_dir
            return str(v)

        env = os.environ.copy()
        env["POLYVERSION_DATA"] = self.encoder.encode(data)

        cmd = tuple(map(replace, self.cmd))

        # create output directory
        output_dir.mkdir(exist_ok=True, parents=True)

        # pre hook
        if self.pre_cmd:
            out, err, rc = await environment.run(*map(replace, self.pre_cmd), env=env)
            if rc:
                raise BuildError from CalledProcessError(rc, " ".join(cmd), out, err)

        # build command
        out, err, rc = await environment.run(*cmd, env=env)

        self.logger.debug("Installation output:\n %s", out)
        if rc:
            raise BuildError from CalledProcessError(rc, " ".join(cmd), out, err)

        # post hook
        if self.post_cmd:
            out, err, rc = await environment.run(*map(replace, self.post_cmd), env=env)
            if rc:
                raise BuildError from CalledProcessError(rc, " ".join(cmd), out, err)


class SphinxBuilder(CommandBuilder):
    """
    A CommandBuilder running `sphinx-build`.

    Parameters
    ----------
    source : PurePath
        The relative source location to pass to the command.
    args : Iterable[str], optional
        The arguments to pass to `sphinx-build`, by default []
    encoder : json.JSONEncoder | None, optional
        The encoder to use for serializing the metadata, by default None
    pre_cmd : Iterable[str | Placeholder], optional
        Additional command to run before `cmd`.
    post_cmd : Iterable[str | Placeholder], optional
        Additional command to run after `cmd`.

    """

    def __init__(
        self,
        source: str | PurePath,
        *,
        args: Iterable[str] = [],
        encoder: json.JSONEncoder | None = None,
        pre_cmd: Iterable[str | Placeholder] | None = None,
        post_cmd: Iterable[str | Placeholder] | None = None,
    ) -> None:
        """
        Init the builder.

        Parameters
        ----------
        source : PurePath
            The relative source location to pass to the command.
        args : Iterable[str], optional
            The arguments to pass to `sphinx-build`, by default []
        encoder : json.JSONEncoder | None, optional
            The encoder to use for serializing the metadata, by default None
        pre_cmd : Iterable[str | Placeholder], optional
            Additional command to run before `cmd`.
        post_cmd : Iterable[str | Placeholder], optional
            Additional command to run after `cmd`.

        """
        cmd: Iterable[str | Placeholder] = [
            "sphinx-build",
            "--color",
            *args,
            Placeholder.SOURCE_DIR,
            Placeholder.OUTPUT_DIR,
        ]
        super().__init__(
            source,
            cmd,
            encoder=encoder,
            pre_cmd=pre_cmd,
            post_cmd=post_cmd,
        )
        self.args = args
