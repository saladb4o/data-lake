"""Two classes of defect that leave no trace at runtime.

1. ``except Exception: pass`` — the failure never reaches a log, so a broken
   parser, a dead endpoint or a swallowed TypeError looks exactly like a
   symbol that legitimately has no data.

2. ``abs(hash(text))`` as a record id — CPython salts str hashing per process
   (PYTHONHASHSEED), so the same article, disclosure or filing gets a new id
   on every restart. Every store keyed on those ids stops deduplicating and
   accumulates the same record over and over.

Both are invisible in a passing test run, which is precisely why they need a
test of their own.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Production code: everything that runs in the app or its tooling. The test
# suite itself is exempt - a mock URL built from hash() harms nobody, and a
# deliberately-empty handler in a test is not a hidden production failure.
_SKIP_DIRS = {".git", "node_modules", "__pycache__", "tests", ".venv", "venv"}

# A handler may stay silent only if the source says so explicitly, with a
# `silent-ok:` marker and a reason, on or beside the `pass`. Today that is only
# for code running before the module's logger exists.
SILENT_MARKER = "silent-ok:"


def _production_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*.py")
        if not _SKIP_DIRS & set(p.relative_to(ROOT).parts)
    )


def _silent_handlers(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or len(node.body) != 1:
            continue
        body = node.body[0]
        if isinstance(body, ast.Pass):
            yield node
        elif (
            isinstance(body, ast.Expr)
            and isinstance(body.value, ast.Constant)
            and body.value.value is Ellipsis
        ):
            yield node


@pytest.mark.parametrize(
    "path", _production_files(), ids=lambda p: str(p)
)
def test_exception_handlers_are_not_silent(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    offenders = []
    for handler in _silent_handlers(tree):
        body_line = handler.body[0].lineno - 1
        window = "\n".join(lines[max(0, body_line - 3): body_line + 2])
        if SILENT_MARKER not in window:
            offenders.append(handler.lineno)

    assert not offenders, (
        f"{path.relative_to(ROOT)} swallows exceptions with no log at "
        f"line(s) {offenders}. Log at debug level and keep the control flow, "
        "or handle the error."
    )


@pytest.mark.parametrize("path", _production_files(), ids=lambda p: str(p))
def test_no_builtin_hash_in_record_identifiers(path: Path):
    """`hash()` of a str is process-salted and must not become an id."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "hash"
    ]
    assert not offenders, (
        f"{path.relative_to(ROOT)} calls the builtin hash() at line(s) "
        f"{offenders}. Use services.stable_identity.stable_hash so the id "
        "survives a restart."
    )


def test_stable_hash_is_deterministic_across_processes():
    """The property the whole module exists for — verified, not asserted."""
    script = (
        "from services.stable_identity import stable_hash;"
        "print(stable_hash('https://example.com/bao-cao-tai-chinh-q3'))"
    )
    seen = set()
    for seed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        out = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT, env=env, capture_output=True, text=True, check=True,
        )
        seen.add(out.stdout.strip())
    assert len(seen) == 1, f"stable_hash varied with PYTHONHASHSEED: {seen}"


def test_builtin_hash_really_does_vary(tmp_path):
    """Guards the premise: if this ever stops varying, the rule is moot."""
    seen = set()
    for seed in ("1", "999"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        out = subprocess.run(
            [sys.executable, "-c", "print(abs(hash('bao-cao-tai-chinh')))"],
            cwd=ROOT, env=env, capture_output=True, text=True, check=True,
        )
        seen.add(out.stdout.strip())
    assert len(seen) > 1, "builtin hash() no longer varies by seed"


def test_stable_hash_bounds_and_type():
    from services.stable_identity import stable_hash, stable_id

    assert stable_hash("abc") >= 0
    assert 0 <= stable_hash("abc", 100000) < 100000
    assert stable_id("press", "abc") == f"press_{stable_hash('abc')}"
    assert stable_hash("abc") != stable_hash("abd")
    # Same input, same answer, within a process too.
    assert stable_hash("abc") == stable_hash("abc")


def test_deprecated_alias_agrees_with_stable_hash():
    from services.stable_identity import stable_hash
    import services.stock_service as ss

    assert ss.deterministic_hash("VCB") == stable_hash("VCB")
