"""
The PHP bundle must run on the PHP a shared host actually has.

A customer's host ran PHP older than 7.4 and the app died with a raw parse error showing a
server path — `unexpected '=>'`, which is what an arrow function looks like to an older parser.
Nothing in the bundle needs 7.4, so the floor is 7.1 and these tests keep it there.

Two separate things are checked, because they fail differently:

  * no file uses syntax newer than the floor. A parse error cannot be caught at runtime, so
    this has to be prevented rather than handled.
  * the version guard is the FIRST thing every entry point requires. PHP parses a whole file
    when it is included, so a check living inside a modern file never runs — the parse error
    happens first. The guard is written in PHP 5-era syntax for the same reason.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PHP_ROOT = ROOT / "deploy" / "php"

#: The oldest PHP the bundle promises to run on.
MIN_PHP = "7.1.0"

#: Entry points a visitor can hit directly. Each must guard before anything modern is parsed.
ENTRY_POINTS = ("index.php", "admin.php")

#: Syntax newer than the floor, with the version that introduced it.
TOO_NEW = [
    (r"\bfn\s*\(", "7.4", "arrow function"),
    (r"(?:public|private|protected)\s+\??(?:array|string|float|int|bool|iterable|self|Slice)\s+\$",
     "7.4", "typed property"),
    (r"\?\?=", "7.4", "null-coalescing assignment"),
    (r"\[\s*\.\.\.\$", "7.4", "array spread"),
    (r"\barray_key_first\s*\(|\barray_key_last\s*\(", "7.3", "array_key_first/last"),
    (r"\bmatch\s*\(\s*[\$\w]", "8.0", "match expression"),
    (r"\?->", "8.0", "nullsafe operator"),
    (r"\bstr_contains\s*\(|\bstr_starts_with\s*\(|\bstr_ends_with\s*\(", "8.0", "PHP 8 string helpers"),
    (r"^\s*(?:readonly|enum)\s", "8.1", "readonly / enum"),
]


def php_files() -> list[Path]:
    return sorted(p for p in PHP_ROOT.rglob("*.php") if "_test" not in p.name and "_verify" not in p.name)


def test_the_bundle_ships_php_files():
    files = php_files()
    assert len(files) >= 8, "the bundle should carry the app, the library and the entry points"


@pytest.mark.parametrize("pattern,version,label", TOO_NEW, ids=[t[2] for t in TOO_NEW])
def test_no_file_uses_syntax_newer_than_the_floor(pattern, version, label):
    offenders = []
    for path in php_files():
        source = path.read_text(encoding="utf-8")
        # Strip comments and here-doc prose so words like "never" in a docblock cannot match.
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        source = re.sub(r"^\s*//.*$", "", source, flags=re.M)
        for match in re.finditer(pattern, source, flags=re.M):
            line = source[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(PHP_ROOT)}:{line} ({label}, needs PHP {version})")
    assert not offenders, "syntax newer than PHP " + MIN_PHP + ":\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_every_entry_point_guards_before_it_parses_anything_modern(entry):
    source = (PHP_ROOT / entry).read_text(encoding="utf-8")
    requires = re.findall(r"require(?:_once)?\s+__DIR__\s*\.\s*'([^']+)'", source)
    assert requires, f"{entry} requires nothing?"
    assert requires[0].endswith("compat.php"), (
        f"{entry} requires {requires[0]} before the version guard; a parse error in that file "
        f"would reach the visitor as a raw server path")


def test_the_guard_itself_parses_on_any_php():
    """It is the one file that must never use anything the target might not understand."""
    source = (PHP_ROOT / "lib" / "compat.php").read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    for pattern, version, label in TOO_NEW:
        assert not re.search(pattern, body, flags=re.M), f"the guard uses {label} (PHP {version})"
    for modern in ("declare(strict_types", "): void", "): array", "?string", "??="):
        assert modern not in body, f"the guard uses {modern!r}, which an old parser may reject"
    assert "version_compare(PHP_VERSION" in body
    assert MIN_PHP in body


@pytest.mark.skipif(shutil.which("php") is None, reason="php CLI not on PATH")
@pytest.mark.parametrize("path", [p.relative_to(PHP_ROOT).as_posix() for p in php_files()])
def test_every_php_file_still_parses(path):
    proc = subprocess.run(["php", "-l", str(PHP_ROOT / path)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout or proc.stderr
