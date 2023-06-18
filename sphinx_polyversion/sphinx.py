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
    SOURCE_DIR = enum.auto()
    OUTPUT_DIR = enum.auto()


class CommandBuilder(Builder[ENV, None]):
    def __init__(
        self,
        source: PurePath,
        cmd: Iterable[str | Placeholder],
        encoder: json.JSONEncoder | None = None,
    ) -> None:
        super().__init__()
        self.cmd = cmd
        self.source = source
        self.logger = logger
        self.encoder = encoder or Encoder()

    async def build(self, environment: ENV, output_dir: Path, data: JSONable) -> None:
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
    def __init__(
        self,
        source: PurePath,
        *,
        args: Iterable[str] = [],
        encoder: json.JSONEncoder | None = None,
    ) -> None:
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
