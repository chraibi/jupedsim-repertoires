# SPDX-License-Identifier: LGPL-3.0-or-later

"""Command line entry point ``jps-repertoires``."""

import argparse
import pathlib
import sys

from jupedsim_repertoires.situations import (
    ExtractError,
    extract_situations,
    output_paths,
)

_SEED_LIMIT = 2**64


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jps-repertoires")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser(
        "extract-situations",
        help="export the decision requests of a run log",
    )
    extract.add_argument("run", type=pathlib.Path, help="run log (JSON Lines)")
    extract.add_argument(
        "--output",
        type=pathlib.Path,
        required=True,
        help="situations file ending in .jsonl; labels and manifest are "
        "written next to it",
    )
    extract.add_argument(
        "--sample",
        type=int,
        help="export N requests, uniform over decision requests, not over "
        "people or time",
    )
    extract.add_argument(
        "--seed",
        type=int,
        help="seed of the sample, 0 <= S < 2**64 (default 0; needs --sample)",
    )
    extract.add_argument(
        "--overwrite", action="store_true", help="replace an existing export"
    )
    return parser


def _check_usage(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.seed is not None and args.sample is None:
        parser.error("--seed requires --sample")
    if args.sample is not None and args.sample < 1:
        parser.error("--sample must be at least 1")
    if args.seed is not None and not 0 <= args.seed < _SEED_LIMIT:
        parser.error("--seed must satisfy 0 <= seed < 2**64")
    try:
        output_paths(args.output)
    except ValueError as err:
        parser.error(str(err))


def main(argv: list[str] | None = None) -> int:
    """Run the command line; return the process exit status."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    _check_usage(parser, args)
    try:
        extract_situations(
            args.run,
            args.output,
            sample=args.sample,
            seed=args.seed or 0,
            overwrite=args.overwrite,
        )
    except ExtractError as err:
        print(f"error[{err.category}]: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
