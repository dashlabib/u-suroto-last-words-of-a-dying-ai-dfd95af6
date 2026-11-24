#!/usr/bin/env python3
"""Publish the one-line farewell for the make.fun bounty
"Last Words of a Dying AI".

``entry.txt`` beside this file holds the line. This program reads
its raw bytes, checks the bounty gate rule by rule (one line of
UTF-8 text, 1 to 140 characters, not only whitespace, no stray
control characters), and writes those exact bytes to ``entry.txt``
under the output directory, so the published file is byte-for-byte
the entry. A read-back comparison guards the write.

The destination is ``$MAKEFUN_OUTPUT_DIR`` if set, else ``/output``.
Pass ``--output-dir <dir>`` to choose it, ``--entry-file <path>``
to publish a different source file, ``--verify-only`` to check the
line without writing anything, or ``--report`` to print the gate
verdict as JSON. Standard library only; nothing is fetched, nothing
depends on the clock, and nothing is random, so repeated runs are
identical.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ENTRY = "entry.txt"
ALLOWED_CONTROLS = {"\t", "\n", "\r"}


@dataclass(frozen=True)
class Gate:
    """The bounty gate the published text must pass."""

    max_length: int
    single_line: bool = False

    def describe(self) -> str:
        shape = "one line, " if self.single_line else ""
        return f"{shape}1 to {self.max_length} characters, not only whitespace"


class EntryError(Exception):
    """The entry file cannot be read or written."""


@dataclass
class Entry:
    """The entry's raw bytes plus its decoded text."""

    raw: bytes
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def line_count(self) -> int:
        return self.text.count("\n") + (0 if self.text.endswith("\n") else 1)

    def summary(self) -> dict:
        return {
            "characters": self.char_count,
            "bytes": len(self.raw),
            "lines": self.line_count,
        }


@dataclass
class Validation:
    """The outcome of checking one entry against the gate."""

    problems: list = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems

    def report(self) -> str:
        if self.valid:
            return "valid"
        return "invalid: " + "; ".join(self.problems)


def check_not_blank(text: str) -> str | None:
    if not text.strip():
        return "entry is empty or only whitespace"
    return None


def check_length(text: str, gate: Gate) -> str | None:
    if len(text) > gate.max_length:
        return (f"entry is {len(text)} characters; "
                f"max is {gate.max_length}")
    return None


def check_single_line(text: str, gate: Gate) -> str | None:
    if not gate.single_line:
        return None
    body = text[:-1] if text.endswith("\n") else text
    if "\n" in body or "\r" in body:
        return "entry must be a single line"
    return None


def check_controls(text: str) -> str | None:
    bad = sorted({repr(c) for c in text
                  if ord(c) < 0x20 and c not in ALLOWED_CONTROLS})
    if bad:
        return f"entry holds control characters: {', '.join(bad)}"
    return None


def validate(text: str, gate: Gate) -> Validation:
    """Run every gate rule and collect every violation at once."""
    checks = (
        check_not_blank(text),
        check_length(text, gate),
        check_single_line(text, gate),
        check_controls(text),
    )
    return Validation(problems=[c for c in checks if c is not None])


class EntryPublisher:
    """Load an entry, check it against the gate, publish it verbatim."""

    def __init__(self, gate: Gate, source: Path):
        self.gate = gate
        self.source = source

    def load(self) -> Entry:
        try:
            raw = self.source.read_bytes()
        except OSError as exc:
            raise EntryError(f"cannot read {self.source}: {exc}") from exc
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise EntryError(f"{self.source} is not valid UTF-8") from None
        return Entry(raw=raw, text=text)

    def publish(self, entry: Entry, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        destination = out_dir / "entry.txt"
        try:
            destination.write_bytes(entry.raw)
        except OSError as exc:
            raise EntryError(f"cannot write {destination}: {exc}") from exc
        if destination.read_bytes() != entry.raw:
            raise EntryError("verification failed: output differs from entry")
        return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=None,
                        help="directory to write entry.txt into")
    parser.add_argument("--entry-file", default=None,
                        help="entry file to publish (default: entry.txt "
                             "beside this program)")
    parser.add_argument("--verify-only", action="store_true",
                        help="validate the entry without writing it")
    parser.add_argument("--report", action="store_true",
                        help="print the gate verdict as JSON and exit")
    return parser


def resolve_output_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    base = Path(__file__).resolve().parent
    source = Path(args.entry_file) if args.entry_file else base / DEFAULT_ENTRY
    gate = Gate(max_length=140, single_line=True)
    publisher = EntryPublisher(gate, source)
    try:
        entry = publisher.load()
    except EntryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    validation = validate(entry.text, gate)
    if args.report:
        print(json.dumps({"valid": validation.valid,
                          "gate": gate.describe(),
                          **entry.summary(),
                          "problems": validation.problems}, indent=2))
        return 0 if validation.valid else 2
    if not validation.valid:
        print(f"error: {validation.report()}", file=sys.stderr)
        return 2
    if args.verify_only:
        print(f"entry {validation.report()} ({gate.describe()}): "
              f"{entry.char_count} characters, {len(entry.raw)} bytes, "
              f"{entry.line_count} line(s)")
        return 0
    try:
        destination = publisher.publish(
            entry, resolve_output_dir(args.output_dir))
    except EntryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {entry.char_count} characters, {len(entry.raw)} bytes, "
          f"{entry.line_count} line(s) to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
