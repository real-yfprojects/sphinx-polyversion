"""The entry point of the module."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from logging import StreamHandler
from pathlib import Path
from typing import Sequence

from sphinx_polyversion.utils import import_file


class ParseKwargs(argparse.Action):
    """Action for keyword, value pairs seperated by equality signs."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        arguments: str | Sequence[str] | None,
        option_string: str | None = None,
    ) -> None:
        """Parse an argument."""
        if not isinstance(arguments, Iterable):
            raise TypeError(
                "Expected iterable of arguments. Use this type with nargs='*'"
            )
        kwargs = getattr(namespace, self.dest, {})
        for option in arguments:
            if "=" not in option:
                parser.error(f"Not a key=value pair: {option}")
            key, value = option.split("=")
            kwargs[key] = value
        setattr(namespace, self.dest, kwargs)


def get_parser(expect_config: bool = True) -> argparse.ArgumentParser:
    """Define cmd line signature."""
    parser = argparse.ArgumentParser(
        description="Build multiple versions of your sphinx docs and merge them into one site."
    )

    # config file
    conf_arg = parser.add_argument(
        "conf",
        type=Path,
        help="Polyversion config file to load. This must be a python file that can be evaluated.",
    )
    if not expect_config:
        conf_arg.nargs = "?"

    # config options
    parser.add_argument(
        "out",
        type=Path,
        help="Output directory to build the merged docs to.",
        nargs="?",
        default=False,
    )
    parser.add_argument(
        "-o",
        "--override",
        nargs="*",
        action=ParseKwargs,
        help="Override config options. Pass them as `key=value` pairs.",
        default={},
    )
    parser.add_argument(
        "-v",
        "--verbosity",
        action="count",
        default=0,
        help="Increase output verbosity (decreases minimum log level). The default log level is ERROR.",
    )
    parser.add_argument(
        "-l",
        "--local",
        "--mock",
        action="store_true",
        help="Build the local version of your docs.",
    )
    return parser


def main() -> None:
    """Run the `poly.py` config file."""
    parser = get_parser()

    args, _ = parser.parse_known_args()
    conf: Path = args.conf

    # handle logging verbosity
    from sphinx_polyversion import logger

    handler = StreamHandler()
    logger.addHandler(handler)
    handler.setLevel(max(10, 40 - 10 * args.verbosity))

    # run config file
    if not conf.is_file():
        parser.error("Config file doesn't exist.")

    import_file(conf)
