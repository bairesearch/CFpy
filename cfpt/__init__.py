"""CFpt package: tools for filtering Python code based on boolean globals."""

from .filtering import (
    FilterSwitchesTransformer,
    load_boolean_globals,
    process_file,
    walk_and_filter,
)

__all__ = [
    "FilterSwitchesTransformer",
    "load_boolean_globals",
    "process_file",
    "walk_and_filter",
]
