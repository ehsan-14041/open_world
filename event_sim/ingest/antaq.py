"""
ANTAQ ingestion and schema audit — schema-agnostic by construction.

The ANTAQ schema has NOT been seen. Every ANTAQ data host disallows this crawler
(`User-agent: ClaudeBot / Disallow: /`), so acquisition stopped at the publisher's policy
and no file was ever opened. See docs/replays/ANTAQ_ACQUISITION.md.

That fact dictates the design. This module must be able to describe a file it has never
seen, so it:

  * discovers filenames rather than expecting them,
  * profiles columns rather than mapping them,
  * treats every guess about column meaning as an explicitly labelled HYPOTHESIS that the
    audit prints for a human to confirm against ANTAQ's own data dictionary,
  * refuses to derive waiting time or reconstruct a queue until a human has recorded that
    confirmation.

The last point is the important one. Two timestamps that look like arrival and berthing are
not a queue measurement until the publisher says what they mean — the project has already
been caught once by a number that was official, precise, and the wrong quantity (Panama's
booking slots).

Usage once files exist:

    python -m event_sim.ingest.antaq register --retrieved-by "..." --retrieved-at 2026-08-10
    python -m event_sim.ingest.antaq audit
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ANTAQ_ROOT = _PROJECT_ROOT / "data" / "external" / "antaq"
RAW_DIR = ANTAQ_ROOT / "raw"
DERIVED_DIR = ANTAQ_ROOT / "derived"
METADATA_DIR = ANTAQ_ROOT / "metadata"
MANIFEST_PATH = METADATA_DIR / "manifest.json"
SEMANTICS_PATH = METADATA_DIR / "column_semantics.json"

#: Delimiters ANTAQ text extracts plausibly use, tried in order of likelihood.
CANDIDATE_DELIMITERS = (";", "\t", ",", "|")

#: Encodings to try, most likely first for Brazilian government text files.
CANDIDATE_ENCODINGS = ("utf-8-sig", "latin-1", "utf-8")

#: UNVERIFIED hypotheses about what ANTAQ columns might mean, based only on the dataset's
#: public description. These are PRINTED BY THE AUDIT FOR A HUMAN TO CONFIRM OR REJECT.
#: Nothing in this module acts on them. A hypothesis is not a mapping.
COLUMN_HYPOTHESES: dict[str, str] = {
    "IDAtracacao": "possible unique berthing/port-call identifier",
    "Data Atracacao": "possible berthing timestamp",
    "Data Chegada": "possible arrival timestamp — CRITICAL: arrival WHERE? anchorage, port limits, or pilot station?",
    "Data Desatracacao": "possible unberthing timestamp",
    "Data Inicio Operacao": "possible operation start",
    "Data Termino Operacao": "possible operation end",
    "Porto Atracacao": "possible port name",
    "Berco": "possible berth identifier",
    "Terminal": "possible terminal identifier",
    "Tipo de Navegacao da Atracacao": "possible navigation type (long haul / cabotage / support)",
}

#: The audit refuses to go further than profiling until a human records these answers.
REQUIRED_SEMANTIC_CONFIRMATIONS = (
    "arrival_column",
    "arrival_meaning",          # what point in space/process does it mark?
    "berthing_column",
    "call_id_column",
    "port_column",
    "timezone",
    "source_of_truth",          # which ANTAQ document confirms the above
)


class AntaqDataUnavailable(FileNotFoundError):
    """Raised when no ANTAQ raw artifact is present."""


class SemanticsNotConfirmed(RuntimeError):
    """Raised when a derivation is attempted before column meanings are human-confirmed."""


# --------------------------------------------------------------------------------------
# Discovery and provenance
# --------------------------------------------------------------------------------------


@dataclass
class RawArtifact:
    """One downloaded file, recorded immutably."""

    path: str
    filename: str
    size_bytes: int
    sha256: str
    retrieved_at: str = ""
    retrieved_by: str = ""
    source: str = "https://estatistica.antaq.gov.br/ea/sense/download.html"
    license_note: str = (
        "Brazilian federal open government data (ANTAQ). Public and free. The publisher's "
        "robots.txt disallows automated AI crawlers, so this file must be obtained by a "
        "human; that is a crawler policy, not a licence restriction."
    )
    coverage: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "filename": self.filename, "size_bytes": self.size_bytes,
            "sha256": self.sha256, "retrieved_at": self.retrieved_at,
            "retrieved_by": self.retrieved_by, "source": self.source,
            "license_note": self.license_note, "coverage": self.coverage,
        }


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _record_path(path: Path) -> str:
    """
    Project-relative where possible, absolute otherwise.

    Raw files normally live under data/external/antaq/raw, but tests and ad-hoc audits may
    point the loader elsewhere; a path outside the project must not crash discovery.
    """
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)


def discover_raw(raw_dir: Path | None = None) -> list[RawArtifact]:
    """
    Find whatever is actually in the raw directory. Filenames are discovered, never assumed.
    """
    base = raw_dir or RAW_DIR
    if not base.is_dir():
        return []
    artifacts: list[RawArtifact] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        artifacts.append(RawArtifact(
            path=_record_path(path),
            filename=path.name,
            size_bytes=path.stat().st_size,
            sha256=_sha256(path),
        ))
    return artifacts


def register(*, retrieved_by: str = "", retrieved_at: str = "",
             raw_dir: Path | None = None,
             manifest_path: Path | None = None) -> dict[str, Any]:
    """
    Write the provenance manifest for whatever raw files exist.

    The manifest is written NEXT TO the raw directory it describes. Registering a custom
    `raw_dir` (as tests do) must never write into the repository's real metadata directory —
    a manifest describing files that live elsewhere is fabricated provenance. This exact
    leak happened once: a unit test left the repository manifest pointing at a synthetic
    zip in a deleted temp directory.
    """
    base = raw_dir or RAW_DIR
    artifacts = discover_raw(base)
    if not artifacts:
        raise AntaqDataUnavailable(
            f"No ANTAQ files in {base}. See docs/replays/ANTAQ_ACQUISITION.md "
            f"for the manual download instructions."
        )
    for artifact in artifacts:
        artifact.retrieved_by = retrieved_by
        artifact.retrieved_at = retrieved_at
    manifest = {
        "dataset": "ANTAQ Estatístico Aquaviário — Atracação",
        "raw_dir": _record_path(base),
        "artifacts": [a.to_dict() for a in artifacts],
        "raw_is_immutable": True,
        "note": (
            "Raw files are never rewritten or normalised in place. All processing writes to "
            "derived/. Re-running register() must reproduce identical checksums."
        ),
    }
    if manifest_path is None:
        # Default: real raw dir -> real metadata dir; any other raw dir -> a sibling file,
        # so the repository manifest can only ever describe the repository's raw layer.
        manifest_path = MANIFEST_PATH if base.resolve() == RAW_DIR.resolve() \
            else base / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def verify_manifest(manifest: dict[str, Any] | None = None) -> list[str]:
    """
    Re-checksum every registered artifact. Any difference means the raw layer was mutated,
    which invalidates every derived result.
    """
    if manifest is None:
        if not MANIFEST_PATH.is_file():
            raise AntaqDataUnavailable(f"No manifest at {MANIFEST_PATH}")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    drift: list[str] = []
    for record in manifest.get("artifacts", []):
        candidate = Path(record["path"])
        path = candidate if candidate.is_absolute() else _PROJECT_ROOT / candidate
        if not path.is_file():
            drift.append(f"{record['filename']}: MISSING")
            continue
        actual = _sha256(path)
        if actual != record["sha256"]:
            drift.append(f"{record['filename']}: checksum changed — raw layer was mutated")
    return drift


# --------------------------------------------------------------------------------------
# Schema profiling — describes, never interprets
# --------------------------------------------------------------------------------------


@dataclass
class ColumnProfile:
    """What a column actually contains. Deliberately carries no inferred meaning."""

    name: str
    non_empty: int = 0
    total: int = 0
    examples: list[str] = field(default_factory=list)
    distinct_sampled: int = 0
    looks_numeric: bool = False
    looks_datetime: bool = False
    hypothesis: str = ""

    @property
    def missing_fraction(self) -> float:
        return 1.0 - (self.non_empty / self.total) if self.total else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.name, "total_rows_sampled": self.total,
            "non_empty": self.non_empty, "missing_fraction": round(self.missing_fraction, 4),
            "distinct_sampled": self.distinct_sampled, "examples": self.examples[:5],
            "looks_numeric": self.looks_numeric, "looks_datetime": self.looks_datetime,
            "unverified_hypothesis": self.hypothesis,
            "inferred_meaning": None,
            "documented_meaning": None,
            "note": "meaning must come from ANTAQ's data dictionary, not from this profile",
        }


def _looks_datetime(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) < 8:
        return False
    digits = sum(c.isdigit() for c in stripped)
    separators = sum(c in "/-:" for c in stripped)
    return digits >= 6 and separators >= 2


def _looks_numeric(value: str) -> bool:
    try:
        float(value.strip().replace(",", "."))
        return True
    except ValueError:
        return False


def _open_text(path: Path) -> Iterator[tuple[str, io.TextIOBase]]:
    """Yield (member_name, text_stream) for a plain text file or every member of a ZIP."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                raw = archive.read(member)
                for encoding in CANDIDATE_ENCODINGS:
                    try:
                        yield member, io.StringIO(raw.decode(encoding))
                        break
                    except UnicodeDecodeError:
                        continue
    else:
        for encoding in CANDIDATE_ENCODINGS:
            try:
                yield path.name, io.StringIO(path.read_text(encoding=encoding))
                break
            except UnicodeDecodeError:
                continue


def sniff_delimiter(header_line: str) -> str:
    """Pick the delimiter that splits the header into the most fields."""
    return max(CANDIDATE_DELIMITERS, key=header_line.count)


def profile_file(path: Path, *, sample_rows: int = 5000) -> list[dict[str, Any]]:
    """
    Profile every member of a raw artifact without interpreting anything.

    Returns one report per contained table. Sampling is capped so an audit stays fast on
    multi-hundred-megabyte extracts.
    """
    reports: list[dict[str, Any]] = []
    for member, stream in _open_text(path):
        first = stream.readline()
        if not first:
            continue
        delimiter = sniff_delimiter(first)
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=delimiter)
        profiles: dict[str, ColumnProfile] = {}
        seen: dict[str, set[str]] = {}
        rows = 0
        for row in reader:
            rows += 1
            for name, value in row.items():
                if name is None:
                    continue
                profile = profiles.setdefault(
                    name, ColumnProfile(name=name, hypothesis=COLUMN_HYPOTHESES.get(name, ""))
                )
                profile.total += 1
                text = (value or "").strip()
                if not text:
                    continue
                profile.non_empty += 1
                bucket = seen.setdefault(name, set())
                if len(bucket) < 1000:
                    bucket.add(text)
                if len(profile.examples) < 5:
                    profile.examples.append(text)
                if profile.non_empty <= 50:
                    profile.looks_datetime = profile.looks_datetime or _looks_datetime(text)
                    profile.looks_numeric = profile.looks_numeric or _looks_numeric(text)
            if rows >= sample_rows:
                break
        for name, profile in profiles.items():
            profile.distinct_sampled = len(seen.get(name, set()))
        reports.append({
            "artifact": path.name,
            "member": member,
            "delimiter": delimiter,
            "rows_sampled": rows,
            "column_count": len(profiles),
            "columns": [p.to_dict() for p in profiles.values()],
        })
    return reports


# --------------------------------------------------------------------------------------
# The gate: no derivation without confirmed semantics
# --------------------------------------------------------------------------------------


def load_semantics(path: Path | None = None) -> dict[str, Any]:
    target = path or SEMANTICS_PATH
    if not target.is_file():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def semantics_confirmed(semantics: dict[str, Any] | None = None) -> list[str]:
    """
    Return what is still missing before any waiting time may be computed.

    Empty list means a human has recorded, with a cited source, what each timestamp means.
    """
    data = semantics if semantics is not None else load_semantics()
    missing = [key for key in REQUIRED_SEMANTIC_CONFIRMATIONS if not data.get(key)]
    if not data.get("confirmed_by"):
        missing.append("confirmed_by")
    return missing


def require_semantics(semantics: dict[str, Any] | None = None) -> None:
    """
    Guard every derivation.

    Raises unless a human has confirmed what the timestamps mean. This is the safeguard
    against repeating the Panama error — computing a precise number from the wrong quantity.
    """
    missing = semantics_confirmed(semantics)
    if missing:
        raise SemanticsNotConfirmed(
            "ANTAQ column semantics are not confirmed; cannot derive waiting time or "
            f"reconstruct a queue. Missing: {missing}. Record them in "
            f"{SEMANTICS_PATH.relative_to(_PROJECT_ROOT)} with the ANTAQ data-dictionary "
            f"reference that establishes each one. Two timestamps are not a queue "
            f"measurement until the publisher says what they mean."
        )


def status() -> dict[str, Any]:
    """Where ANTAQ ingestion currently stands. Safe to call with no data present."""
    artifacts = discover_raw()
    semantics = load_semantics()
    # A manifest with no matching raw files is fabricated provenance and must be surfaced
    # loudly, not tolerated: it claims an acquisition that did not survive.
    stale_manifest = MANIFEST_PATH.is_file() and (
        not artifacts or bool(verify_manifest())
    )
    return {
        "stale_manifest": stale_manifest,
        "raw_artifacts": len(artifacts),
        "raw_dir": str(RAW_DIR.relative_to(_PROJECT_ROOT)),
        "manifest_present": MANIFEST_PATH.is_file(),
        "semantics_confirmed": not semantics_confirmed(semantics),
        "missing_semantics": semantics_confirmed(semantics),
        "can_profile": bool(artifacts),
        "can_derive_waiting_time": bool(artifacts) and not semantics_confirmed(semantics),
        "blocker": (
            "no raw data — publisher robots.txt disallows this crawler; a human must "
            "download the files (docs/replays/ANTAQ_ACQUISITION.md)"
            if not artifacts else
            "column semantics not yet confirmed against ANTAQ's data dictionary"
            if semantics_confirmed(semantics) else None
        ),
    }


def _cli(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "register", "audit"))
    parser.add_argument("--retrieved-by", default="")
    parser.add_argument("--retrieved-at", default="")
    args = parser.parse_args(argv)

    if args.command == "status":
        print(json.dumps(status(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "register":
        print(json.dumps(register(retrieved_by=args.retrieved_by,
                                  retrieved_at=args.retrieved_at), indent=2, ensure_ascii=False))
        return 0

    artifacts = discover_raw()
    if not artifacts:
        raise AntaqDataUnavailable(
            "Nothing to audit. See docs/replays/ANTAQ_ACQUISITION.md."
        )
    reports = [r for a in artifacts for r in profile_file(_PROJECT_ROOT / a.path)]
    print(json.dumps(reports, indent=2, ensure_ascii=False)[:20000])
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
