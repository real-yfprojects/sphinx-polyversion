"""The entry point of the module."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
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


def get_parser() -> argparse.ArgumentParser:
    """Define cmd line signature."""
    parser = argparse.ArgumentParser(
        description="Build multiple versions of your sphinx docs and merge them into one site."
    )

    # config file
    parser.add_argument(
        "conf",
        type=Path,
        help="Polyversion config file to load. This must be a python file that can be evaluated.",
    )

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
    return parser


def main() -> None:
    """Run the `poly.py` config file."""
    parser = get_parser()

    args, _ = parser.parse_known_args()
    conf: Path = args.conf

    if not conf.is_file():
        parser.error("Config file doesn't exist.")

    import_file(conf)