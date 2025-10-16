"""Command-line interface for filtering inactive code based on boolean globals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:  # Allow running as `python cli.py` without package installation
    from .filtering import load_boolean_globals, walk_and_filter
except ImportError:  # pragma: no cover - execution convenience
    import sys

    CURRENT_DIR = Path(__file__).resolve().parent
    if str(CURRENT_DIR) not in sys.path:
        sys.path.insert(0, str(CURRENT_DIR))
    from filtering import load_boolean_globals, walk_and_filter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Strip code branches guarded by boolean switches defined in a "
            "global definitions module."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Root directory of the Python project to filter.",
    )
    parser.add_argument(
        "global_defs",
        type=Path,
        help="Path to the global definitions Python file containing boolean switches.",
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="Directory where the filtered project will be written.",
    )
    parser.add_argument(
        "--no-copy-global-defs",
        dest="copy_globals",
        action="store_false",
        help="Do not copy the global definitions file into the destination tree.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational output.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    bool_map = load_boolean_globals(args.global_defs)

    if not args.quiet:
        print("Boolean switches loaded:")
        print(json.dumps(bool_map, indent=2, sort_keys=True))

    global_defs_path = args.global_defs if args.copy_globals else None
    walk_and_filter(args.source, args.destination, bool_map, global_defs_path)

    if not args.quiet:
        print(f"Filtered project written to: {args.destination}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
