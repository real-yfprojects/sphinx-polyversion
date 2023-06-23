"""Builder Implementations for running sphinx."""

from __future__ import annotations

import enum
import os
from logging import getLogger
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Any, Iterable

from sphinx_polyversion.builder import ENV, Builder, BuildError
from sphinx_polyversion.json import Encoder, JSONable

if TYPE_CHECKING:
    import json
    from pathlib import Path, PurePath

logger = getLogger(__name__)


class Placeholder(enum.Enum):
    """Placeholders that can be used in commands."""

    #: represents the location of the source files to render the docs from
    SOURCE_DIR = enum.auto()
    #: represents the output location to render the docs to
    OUTPUT_DIR = enum.auto()


class CommandBuilder(Builder[ENV, None]):
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
    """

    def __init__(
        self,
        source: PurePath,
        cmd: Iterable[str | Placeholder],
        encoder: json.JSONEncoder | None = None,
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
        """
        super().__init__()
        self.cmd = cmd
        self.source = source
        self.logger = logger
        self.encoder = encoder or Encoder()

    async def build(self, environment: ENV, output_dir: Path, data: JSONable) -> None:
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

        out, err, rc = await environment.run(*cmd, env=env)

        self.logger.debug("Installation output:\n %s", out)
        if rc:
            raise BuildError from CalledProcessError(rc, " ".join(cmd), out, err)


class SphinxBuilder(CommandBuilder[ENV]):
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
    """

    def __init__(
        self,
        source: PurePath,
        *,
        args: Iterable[str] = [],
        encoder: json.JSONEncoder | None = None,
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
        """
        cmd: Iterable[str | Placeholder] = [
            "sphinx-build",
            "--color",
            *args,
            Placeholder.SOURCE_DIR,
            Placeholder.OUTPUT_DIR,
        ]
        super().__init__(source, cmd, encoder=encoder)
        self.args = args
        self.source = source
