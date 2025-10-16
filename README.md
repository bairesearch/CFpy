# CFpt

CFpt is a small utility inspired by the Baxter AI Code Folder tooling. It filters a
Python codebase by removing branches that are disabled via boolean switches defined
in a ``globalDefs.py`` module. The tool executes the globals module so that dynamic
assignments are respected and then rewrites every ``if`` statement whose condition
can be decided statically from those switches.

## Requirements

* Python 3.9+
* [LibCST](https://libcst.readthedocs.io/) (`pip install libcst`)

## Usage

```bash
python -m cfpt.cli \
    path/to/source \
    path/to/source/globalDefs.py \
    path/to/output
```

The command prints the resolved boolean switches, rewrites the project into the
``path/to/output`` directory, and copies the ``globalDefs.py`` file to the same
relative location in the output tree. Use ``--no-copy-global-defs`` if the globals
file should not be copied.

The destination directory must not be located inside the source tree.

Set ``--quiet`` to suppress informational output.

## Library API

The ``cfpt.filtering`` module exposes utility functions for programmatic use:

* ``load_boolean_globals(path)`` – execute the globals module and return a
  ``dict[str, bool]`` containing all boolean switches.
* ``process_file(src_path, dst_path, bool_map)`` – rewrite a single Python file.
* ``walk_and_filter(src_dir, dst_dir, bool_map, global_defs_path=None)`` – rewrite
  an entire directory tree.

## Disclaimer

The static simplifications are conservative: only simple conditions composed of the
boolean switches, ``not``, ``and``, ``or``, comparisons against ``True``/``False``,
parentheses, and dotted attribute access (``module.FLAG``) are recognised. Conditions
that fall outside of these patterns are left untouched in the output.
