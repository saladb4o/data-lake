"""No test may rebind a module attribute without monkeypatch.

A test that assigns straight onto an imported module has no teardown, so
its stub outlives it. Everything that runs afterwards then measures the
stub instead of the code - and with pytest-randomly deciding the order,
which tests those are changes run to run.

It does not fail. That is what makes it worth a guard: the suite stays
green while quietly testing something else. One instance of this replaced
the VNDIRECT fetch and disabled the cache for a whole session, which sent
later tests to the network and turned a ten-minute suite into a crawl.

Only bare assignment is caught. monkeypatch.setattr, local variables and
attributes on objects a test made itself are all fine.
"""
import ast
import pathlib

import pytest

TESTS = pathlib.Path(__file__).resolve().parent

#: Modules a test is allowed to have imported and then written to. Empty
#: on purpose: there is no such module, and an entry here needs a reason
#: beside it.
ALLOWED: dict = {}


def _module_names(tree):
    """Names bound by `import x` / `from x import y` in this file."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _offences(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = _module_names(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AugAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [
            node.target]
        for target in targets:
            if not isinstance(target, ast.Attribute):
                continue
            # Walk to the root of a.b.c
            root = target
            while isinstance(root, ast.Attribute):
                root = root.value
            if not isinstance(root, ast.Name):
                continue
            if root.id in imported and root.id not in ALLOWED:
                found.append((root.id, node.lineno))
    return found


@pytest.mark.parametrize(
    "path", sorted(TESTS.glob("test_*.py")), ids=lambda p: p.name)
def test_it_does_not_rebind_an_imported_module(path):
    offences = _offences(path)
    assert not offences, "\n".join(
        f"{path.name}:{line} assigns onto imported {name!r};"
        f" use monkeypatch.setattr so it is undone"
        for name, line in offences)


class TestTheGuardWorks:
    def test_it_catches_a_bare_assignment(self, tmp_path):
        # Otherwise the parametrised test above could be passing because
        # it detects nothing at all.
        offender = tmp_path / "test_x.py"
        offender.write_text("import os\nos.sep = '/'\n", encoding="utf-8")
        assert _offences(offender) == [("os", 2)]

    def test_it_allows_monkeypatch(self, tmp_path):
        ok = tmp_path / "test_y.py"
        ok.write_text("import os\ndef test_a(monkeypatch):\n"
                      "    monkeypatch.setattr(os, 'sep', '/')\n",
                      encoding="utf-8")
        assert _offences(ok) == []

    def test_it_leaves_local_objects_alone(self, tmp_path):
        ok = tmp_path / "test_z.py"
        ok.write_text("class C:\n    pass\n\ndef test_a():\n"
                      "    c = C()\n    c.x = 1\n", encoding="utf-8")
        assert _offences(ok) == []
