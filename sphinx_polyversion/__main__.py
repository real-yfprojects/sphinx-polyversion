import asyncio
from argparse import ArgumentParser
from functools import partial
from pathlib import Path
from typing import cast

from sphinx_polyversion.driver import DefaultDriver
from sphinx_polyversion.git import Git, file_predicate
from sphinx_polyversion.json import Encoder, std_hook
from sphinx_polyversion.pyvenv import Poetry
from sphinx_polyversion.sphinx import SphinxBuilder

parser = ArgumentParser()
parser.add_argument("src", type=Path)
parser.add_argument("out", type=Path)

args = parser.parse_args()

root = asyncio.run(Git.root(Path.cwd()))
src = cast(Path, args.src).absolute().relative_to(root)

asyncio.run(
    DefaultDriver(
        Path.cwd(),
        args.out,
        vcs=Git(
            branch_regex="master",
            tag_regex=".*",
            buffer_size=6 * 10**7,
            predicate=file_predicate([src]),
        ),
        builder=SphinxBuilder(
            src,
            encoder=partial(Encoder, std_hook),  # type:ignore
        ),
        env=partial(Poetry, args=["--sync"]),
        namer=lambda r: r.name,  # type:ignore
    ).run()
)
