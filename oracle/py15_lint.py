"""Pre-flight lint for scripts that run inside stbc.exe's Python 1.5.2.

A syntax error in-game opens the TG debug console and freezes the run, so catch the
constructs that Python 3 accepts but 1.5 rejects before deploying.  Checks (AST-based):
continue inside a try body; f-strings; True/False/None as names in comparisons is fine but
True/False literals are not 1.5; conditional expressions; comprehensions; with; augmented
assignment; 'import x as y'; keyword-only args; nonlocal; lambda/def default-free closures
are not detectable statically and are not checked.
"""
import ast
import sys
from pathlib import Path


class V(ast.NodeVisitor):
    def __init__(self, path):
        self.path, self.errs, self.try_depth = path, [], 0

    def err(self, node, msg):
        self.errs.append(f"{self.path}:{node.lineno}: {msg}")

    def visit_Try(self, node):
        self.try_depth += 1
        for n in node.body:
            self.visit(n)
        self.try_depth -= 1
        for h in node.handlers:
            self.visit(h)
        for n in node.orelse + node.finalbody:
            self.visit(n)

    def _loop(self, node):
        saved, self.try_depth = self.try_depth, 0
        self.generic_visit(node)
        self.try_depth = saved
    visit_For = visit_While = _loop

    def visit_FunctionDef(self, node):
        saved, self.try_depth = self.try_depth, 0
        if node.args.kwonlyargs:
            self.err(node, "keyword-only arguments")
        self.generic_visit(node)
        self.try_depth = saved

    def visit_Continue(self, node):
        if self.try_depth:
            self.err(node, "'continue' inside a try body (SyntaxError in Python 1.5)")

    def visit_JoinedStr(self, node): self.err(node, "f-string")
    def visit_IfExp(self, node): self.err(node, "conditional expression")
    def visit_ListComp(self, node): self.err(node, "list comprehension")
    def visit_DictComp(self, node): self.err(node, "dict comprehension")
    def visit_SetComp(self, node): self.err(node, "set comprehension")
    def visit_GeneratorExp(self, node): self.err(node, "generator expression")
    def visit_With(self, node): self.err(node, "with statement")
    def visit_AugAssign(self, node): self.err(node, "augmented assignment (+= etc.)")
    def visit_Nonlocal(self, node): self.err(node, "nonlocal")

    def visit_Constant(self, node):
        if node.value is True or node.value is False:
            self.err(node, "True/False literal")

    def visit_Import(self, node):
        for a in node.names:
            if a.asname:
                self.err(node, "import ... as")
    visit_ImportFrom = visit_Import


import re


def normalise(src):
    """Rewrite valid-in-1.5 statements Python 3 cannot parse into equivalents of the same
    line count: exec/print statements and 'except E, e:'."""
    src = src.replace("\t", "    ")
    src = re.sub(r"^(\s*)exec (.+?) in (.+)$", r"\1exec(\2, \3)", src, flags=re.M)
    src = re.sub(r"^(\s*)print (.+)$", r"\1print(\2)", src, flags=re.M)
    src = re.sub(r"^(\s*)print$", r"\1print()", src, flags=re.M)
    src = re.sub(r"except\s+([\w.]+)\s*,\s*(\w+)\s*:", r"except \1 as \2:", src)
    src = re.sub(r"(\d)L\b", r"\1", src)
    return src


def lint(paths):
    errs = []
    for p in paths:
        src = Path(p).read_text(encoding="latin-1")
        try:
            tree = ast.parse(normalise(src))
        except SyntaxError as e:
            errs.append(f"{p}:{e.lineno}: cannot parse (even after 1.5 normalisation): {e.msg}")
            continue
        v = V(p)
        v.visit(tree)
        errs += v.errs
    return errs


if __name__ == "__main__":
    files = sys.argv[1:] or [str(x) for x in (Path(__file__).parent / "scripts").rglob("*.py")]
    e = lint(files)
    print("\n".join(e) if e else f"py15 lint: {len(files)} files OK")
    sys.exit(1 if e else 0)
