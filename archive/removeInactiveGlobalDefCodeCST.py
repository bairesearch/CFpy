#!/usr/bin/env python3
# removeInactiveGlobalDefCodeCST.py
#
# Requires:  pip install libcst
#
# Tab\u2011indented, lower\u2011camel variable names (per your preferences).

# ----------------------------------------------------------
# User\u2011supplied parameters (inserted exactly as given)
# ----------------------------------------------------------
sourceFolder = "source"
globalDefsFilename = "AEANNpt_AEANN_globalDefs"
globalDefsFilenameFull = globalDefsFilename + ".py"
globalDefsFilenameFullPath = sourceFolder + "/" + globalDefsFilenameFull

# Destination for the stripped project
filteredFolder = "filtered_source"
# ----------------------------------------------------------

import importlib.util, os, pathlib, sys
import libcst as cst
from libcst import FlattenSentinel, RemoveFromParent

# ----------------------------------------------------------
# Helper: load booleans from globalDefs.py
# ----------------------------------------------------------
def loadBooleanGlobals(globalDefsPath: str) -> dict[str, bool]:
	spec = importlib.util.spec_from_file_location(
		pathlib.Path(globalDefsPath).stem, globalDefsPath)
	if spec is None or spec.loader is None:
		raise RuntimeError(f"Cannot import {globalDefsPath}")
	globalModule = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = globalModule
	spec.loader.exec_module(globalModule)				# runs dynamic logic
	return {
		name: val for name, val in vars(globalModule).items()
		if isinstance(val, bool)
	}

# ----------------------------------------------------------
# CST transformer that strips disabled branches
# ----------------------------------------------------------
class FilterSwitchesTransformer(cst.CSTTransformer):
	def __init__(self, boolMap: dict[str, bool]):
		self.boolMap = boolMap
		self._stack: list[cst.CSTNode] = []		# track parents

	# ---------- stack bookkeeping ----------
	def visit_If(self, node):			# push
		self._stack.append(node)

	def leave_If(self, originalNode: cst.If, updatedNode: cst.If):
		# parent before we pop
		parent = self._stack[-2] if len(self._stack) >= 2 else None
		# true if *this* If occurs in parent.orelse
		inOrelse = isinstance(parent, cst.If) and parent.orelse is originalNode

		decision = self._evalTest(originalNode.test)

		# ---- keep / drop logic -----------------------------------------
		if decision is None:				# cannot decide statically
			newNode = updatedNode

		elif decision:						# condition True
			body = updatedNode.body.body
			if inOrelse:
				newNode = self._wrap_as_else(body)
			else:
				newNode = FlattenSentinel(body) if body else RemoveFromParent()

		else:								# condition False
			if originalNode.orelse is None:			# no else/elif
				newNode = RemoveFromParent()
			else:
				elseBody = originalNode.orelse
				if isinstance(elseBody, cst.If):	# `elif` chain
					# keep nested If; it will be simplified in its own leave_If
					newNode = elseBody
				else:								# regular Else
					body = elseBody.body.body
					if inOrelse:
						newNode = self._wrap_as_else(body)
					else:
						newNode = FlattenSentinel(body) if body else RemoveFromParent()

		self._stack.pop()					# pop before returning
		return newNode

	# ---------- helpers ----------
	def _evalTest(self, node: cst.CSTNode):
		if isinstance(node, cst.Name) and node.value in self.boolMap:
			return self.boolMap[node.value]
		if (isinstance(node, cst.UnaryOperation)
				and isinstance(node.operator, cst.Not)
				and isinstance(node.expression, cst.Name)
				and node.expression.value in self.boolMap):
			return not self.boolMap[node.expression.value]
		return None				# unsupported expression

	def _wrap_as_else(self, body):
		# Parent expects If|Else; convert kept statements into an Else block
		if not body:
			body = [cst.SimpleStatementLine([cst.Pass()])]
		return cst.Else(body=cst.IndentedBlock(body=body))

# ----------------------------------------------------------
# File / dir helpers
# ----------------------------------------------------------
def processFile(srcPath: pathlib.Path, dstPath: pathlib.Path, boolMap: dict[str, bool]):
	with srcPath.open("r", encoding="utf-8") as f:
		code = f.read()
	tree = cst.parse_module(code)
	newTree = tree.visit(FilterSwitchesTransformer(boolMap))
	dstPath.parent.mkdir(parents=True, exist_ok=True)
	dstPath.write_text(newTree.code, encoding="utf-8")

def walkAndFilter(srcDir: str, dstDir: str, boolMap: dict[str, bool]):
	for root, _, files in os.walk(srcDir):
		for fname in files:
			if fname.endswith(".py"):
				srcPath = pathlib.Path(root, fname)
				rel = srcPath.relative_to(srcDir)
				dstPath = pathlib.Path(dstDir, rel)

				# copy the globals file verbatim
				if rel.name == globalDefsFilenameFull:
					dstPath.parent.mkdir(parents=True, exist_ok=True)
					dstPath.write_text(srcPath.read_text(encoding="utf-8"))
				else:
					processFile(srcPath, dstPath, boolMap)

# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
if __name__ == "__main__":
	boolMap = loadBooleanGlobals(globalDefsFilenameFullPath)
	print("Boolean switches loaded:")
	for k, v in boolMap.items():
		print(f"\t{k} = {v}")
	walkAndFilter(sourceFolder, filteredFolder, boolMap)
	print(f"\nStripped code written to: {filteredFolder}")
