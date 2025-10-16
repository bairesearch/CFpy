"""Core logic for stripping inactive code based on boolean globals."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterable, Iterator, Optional

import libcst as cst
from libcst import FlattenSentinel, RemoveFromParent


BooleanMap = Dict[str, bool]


class GlobalDefLoadError(RuntimeError):
    """Raised when the globals module cannot be imported."""


def load_boolean_globals(global_defs_path: Path) -> BooleanMap:
    """Import ``global_defs_path`` and return all boolean globals.

    The module is executed so that dynamically assigned values are resolved.
    """

    path = Path(global_defs_path)
    if not path.exists():
        raise GlobalDefLoadError(f"Global definitions file not found: {path}")

    module_name = path.stem
    parent = str(path.parent)
    remove_from_sys_path = False
    if parent and parent not in sys.path:
        sys.path.insert(0, parent)
        remove_from_sys_path = True

    previous_module: Optional[ModuleType] = sys.modules.pop(module_name, None)
    module: Optional[ModuleType] = None

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            raise GlobalDefLoadError(
                f"Unable to load module specification for {module_name!r}"
            )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - defensive programming
        raise GlobalDefLoadError(
            f"Failed to import boolean globals from {path}: {exc}"
        ) from exc
    finally:
        if remove_from_sys_path:
            try:
                sys.path.remove(parent)
            except ValueError:
                pass
        if previous_module is not None:
            sys.modules[module_name] = previous_module
        elif module is not None and sys.modules.get(module_name) is module:
            sys.modules.pop(module_name, None)

    if module is None:
        raise GlobalDefLoadError(
            f"Module {module_name!r} could not be imported from {path}"
        )

    bool_map: BooleanMap = {
        name: value
        for name, value in vars(module).items()
        if isinstance(value, bool)
    }

    return bool_map


class _ConditionEvaluator:
    """Evaluate supported conditional expressions against a boolean map."""

    def __init__(self, bool_map: BooleanMap):
        self.bool_map = bool_map

    def evaluate(self, node: cst.CSTNode) -> Optional[bool]:
        if isinstance(node, cst.Name):
            return self.bool_map.get(node.value)
        if isinstance(node, cst.Attribute) and isinstance(node.attr, cst.Name):
            return self.bool_map.get(node.attr.value)
        if isinstance(node, cst.UnaryOperation) and isinstance(node.operator, cst.Not):
            inner = self.evaluate(node.expression)
            return None if inner is None else not inner
        if isinstance(node, cst.BooleanOperation):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if isinstance(node.operator, cst.And):
                if left is False or right is False:
                    return False
                if left is True and right is True:
                    return True
                return None
            if isinstance(node.operator, cst.Or):
                if left is True or right is True:
                    return True
                if left is False and right is False:
                    return False
                return None
        if isinstance(node, cst.Comparison) and len(node.comparisons) == 1:
            left_val = self.evaluate(node.left)
            comp = node.comparisons[0]
            right_val: Optional[bool]
            if isinstance(comp.comparator, cst.Name):
                if comp.comparator.value in {"True", "False"}:
                    right_val = comp.comparator.value == "True"
                else:
                    right_val = self.bool_map.get(comp.comparator.value)
            elif isinstance(comp.comparator, cst.Boolean):
                right_val = comp.comparator.value
            else:
                right_val = None
            if left_val is None or right_val is None:
                return None
            if isinstance(comp.operator, (cst.Equal, cst.Is)):
                return left_val == right_val
            if isinstance(comp.operator, (cst.NotEqual, cst.IsNot)):
                return left_val != right_val
        if isinstance(node, cst.ParenthesizedExpression):
            return self.evaluate(node.expression)
        if isinstance(node, cst.Boolean):
            return node.value
        return None


class FilterSwitchesTransformer(cst.CSTTransformer):
    """Remove inactive branches guarded by boolean globals."""

    def __init__(self, bool_map: BooleanMap):
        self.bool_map = bool_map
        self._stack: list[cst.CSTNode] = []
        self._evaluator = _ConditionEvaluator(bool_map)

    def visit_If(self, node: cst.If) -> Optional[bool]:  # pragma: no cover - libCST API
        self._stack.append(node)
        return True

    def leave_If(self, original_node: cst.If, updated_node: cst.If) -> cst.CSTNode:
        parent = self._stack[-2] if len(self._stack) >= 2 else None
        in_orelse = isinstance(parent, cst.If) and parent.orelse is original_node
        decision = self._evaluator.evaluate(original_node.test)

        if decision is None:
            result = updated_node
        elif decision:
            body = list(updated_node.body.body)
            result = self._wrap_or_flatten(body, in_orelse)
        else:
            orelse = updated_node.orelse
            if orelse is None:
                result = RemoveFromParent()
            elif isinstance(orelse, cst.If):
                result = orelse
            else:
                body = list(orelse.body.body)
                result = self._wrap_or_flatten(body, in_orelse)

        self._stack.pop()
        return result

    @staticmethod
    def _wrap_or_flatten(
        body: Iterable[cst.BaseStatement], in_orelse: bool
    ) -> cst.CSTNode:
        statements = list(body)
        if in_orelse:
            if not statements:
                statements = [cst.SimpleStatementLine([cst.Pass()])]
            return cst.Else(body=cst.IndentedBlock(body=statements))
        if not statements:
            return RemoveFromParent()
        if len(statements) == 1:
            return statements[0]
        return FlattenSentinel(statements)


def process_file(src_path: Path, dst_path: Path, bool_map: BooleanMap) -> None:
    code = src_path.read_text(encoding="utf-8")
    tree = cst.parse_module(code)
    new_tree = tree.visit(FilterSwitchesTransformer(bool_map))
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(new_tree.code, encoding="utf-8")


def _iter_python_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in filenames:
            if filename.endswith(".py"):
                yield Path(dirpath, filename)


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def walk_and_filter(
    src_dir: Path,
    dst_dir: Path,
    bool_map: BooleanMap,
    global_defs_path: Optional[Path] = None,
) -> None:
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)
    if _is_relative_to(dst_dir, src_dir):
        raise ValueError("Destination directory must not be inside the source directory")
    global_defs_path = Path(global_defs_path) if global_defs_path else None
    global_defs_rel = (
        global_defs_path.relative_to(src_dir)
        if global_defs_path is not None and _is_relative_to(global_defs_path, src_dir)
        else None
    )

    for src_path in _iter_python_files(src_dir):
        rel_path = src_path.relative_to(src_dir)
        dst_path = dst_dir / rel_path
        if global_defs_rel is not None and rel_path == global_defs_rel:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_text(src_path.read_text(encoding="utf-8"))
        else:
            process_file(src_path, dst_path, bool_map)
