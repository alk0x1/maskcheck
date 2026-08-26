"""``maskcheck``: run the conformance properties against schemas you supply.

The sweep in :mod:`fuzzer.sweep` answers a research question, over generated schemas,
across the whole engine and tokenizer matrix. This command answers an operational one:
does the engine I am about to deploy handle *my* schemas correctly, on *my* tokenizer.

It reuses the drivers unchanged. What it adds is the part that was previously implicit
in a notebook: finding the schemas, producing valid documents for them, deciding what
counts as a distinct cause, and printing a result that means something to someone who
has never seen this repository.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from hypothesis import HealthCheck, given, seed as hypothesis_seed, settings
from hypothesis import strategies as st

from fuzzer.engines.base import CapabilityGap, CompilationFailed
from fuzzer.engines.registry import (
    ENGINE_NAMES,
    EngineUnavailable,
    engine_version,
    load_engine,
)
from fuzzer.findings import Violation
from fuzzer.generators.instances import instances
from fuzzer.oracle.validator import check_schema, validate_text
from fuzzer.properties.completeness import check_completeness_variants
from fuzzer.properties.soundness import check_soundness
from fuzzer.report import Occurrence, group_by_cause, render_block
from fuzzer.tokenizers import load_tokenizer, resolve_tokenizer_id

PROPERTIES = ("completeness", "soundness")

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2


class UsageError(Exception):
    """A problem with the invocation or its inputs, not with an engine."""


@dataclass
class SchemaFile:
    source: str
    schema: dict


@dataclass
class PropertyTally:
    checks: int = 0
    skipped: int = 0
    inconclusive: int = 0
    violations: list[Occurrence] = field(default_factory=list)


@dataclass
class RunTally:
    schemas_checked: int = 0
    schemas_skipped: int = 0
    skips: list[str] = field(default_factory=list)
    completeness: PropertyTally = field(default_factory=PropertyTally)
    soundness: PropertyTally = field(default_factory=PropertyTally)

    def tally(self, name: str) -> PropertyTally:
        return getattr(self, name)

    def occurrences(self, fatal: tuple[str, ...]) -> list[Occurrence]:
        found: list[Occurrence] = []
        for name in PROPERTIES:
            if name in fatal:
                found.extend(self.tally(name).violations)
        return found

    @property
    def all_occurrences(self) -> list[Occurrence]:
        return [*self.completeness.violations, *self.soundness.violations]


def discover_schemas(pattern: str) -> list[SchemaFile]:
    """Read JSON Schema documents from a file, a directory, or a glob.

    Ordering is sorted rather than filesystem order so that two runs over the same
    directory report their causes in the same sequence and can be diffed.
    """
    path = Path(pattern)
    if path.is_dir():
        matches = sorted(str(p) for p in path.rglob("*.json"))
    elif path.is_file():
        matches = [str(path)]
    else:
        matches = sorted(glob.glob(pattern, recursive=True))
        matches = [m for m in matches if os.path.isfile(m)]

    if not matches:
        raise UsageError(f"no schema files matched {pattern!r}")

    found: list[SchemaFile] = []
    for match in matches:
        try:
            schema = json.loads(Path(match).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise UsageError(f"{match}: could not read as JSON: {exc}") from exc
        if not isinstance(schema, dict):
            raise UsageError(f"{match}: expected one JSON Schema object per file")
        found.append(SchemaFile(source=match, schema=schema))
    return found


def generate_instances(schema: dict, *, count: int, seed: int) -> list[str]:
    """Valid documents for ``schema``, or an empty list if none could be produced.

    Every candidate is checked against the reference validator before it is returned.
    The instance generator covers the subset of JSON Schema this project generates,
    so on a caller's schema it can emit a document that does not satisfy some keyword
    it does not model, and feeding that to the completeness driver would manufacture a
    violation out of a harness limitation.
    """
    produced: list[str] = []

    @hypothesis_seed(seed)
    @settings(
        max_examples=count,
        deadline=None,
        database=None,
        suppress_health_check=list(HealthCheck),
    )
    @given(st.data())
    def collect(data):
        produced.append(data.draw(instances(schema)))

    try:
        collect()
    except Exception:
        # An unsupported construct makes the strategy itself unbuildable. That is a
        # coverage gap in this harness, reported as a skip by the caller.
        return []

    unique = list(dict.fromkeys(produced))
    return [text for text in unique if validate_text(schema, text)]


def run_completeness(
    tally: RunTally, engine, entry: SchemaFile, tokenizer_id: str, args
) -> None:
    documents = generate_instances(
        entry.schema, count=args.instances, seed=args.seed
    )
    if not documents:
        tally.completeness.skipped += 1
        tally.skips.append(
            f"{entry.source}: completeness skipped, "
            "could not generate a valid document for this schema"
        )
        return

    for document in documents:
        try:
            result = check_completeness_variants(
                engine, entry.schema, document, tokenizer_id
            )
        except (CapabilityGap, CompilationFailed) as exc:
            tally.completeness.skipped += 1
            tally.skips.append(f"{entry.source}: completeness skipped, {exc}")
            return
        except Exception as exc:
            tally.completeness.skipped += 1
            tally.skips.append(f"{entry.source}: completeness errored, {exc}")
            return
        tally.completeness.checks += 1
        _record(tally.completeness, result.canonical.violations, entry.source)


def run_soundness(
    tally: RunTally, engine, entry: SchemaFile, tokenizer_id: str, args
) -> None:
    try:
        result = check_soundness(
            engine,
            entry.schema,
            tokenizer_id,
            walks=args.walks,
            max_steps=args.max_steps,
            seed=args.seed,
        )
    except (CapabilityGap, CompilationFailed) as exc:
        tally.soundness.skipped += 1
        tally.skips.append(f"{entry.source}: soundness skipped, {exc}")
        return
    except Exception as exc:
        tally.soundness.skipped += 1
        tally.skips.append(f"{entry.source}: soundness errored, {exc}")
        return
    tally.soundness.checks += result.walks_completed
    # A walk that ran out of token budget before finishing a document proves nothing
    # either way. Counting it as a check would overstate the coverage of this run.
    tally.soundness.inconclusive += result.walks_inconclusive
    _record(tally.soundness, result.violations, entry.source)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _record(tally: PropertyTally, violations: list[Violation], source: str) -> None:
    """File violations, holding back the ones this harness cannot honestly judge.

    A random walk may accept byte-level tokens that split a multi-byte character, and
    decoding those to text yields U+FFFD. The document in such a report is not the
    document the engine produced, so calling it a soundness violation would blame the
    engine for a limitation of a string-level oracle. Those are counted as
    inconclusive and named in the summary instead of being reported or dropped.
    """
    for violation in violations:
        if "\ufffd" in violation.instance:
            tally.inconclusive += 1
            continue
        tally.violations.append(Occurrence(violation=violation, source=source))


def verify(args, out) -> int:
    try:
        engine = load_engine(args.engine)
    except EngineUnavailable as exc:
        raise UsageError(str(exc)) from exc

    entries = discover_schemas(args.schemas)
    tokenizer_id = resolve_tokenizer_id(args.tokenizer, revision=args.revision)
    try:
        tokenizer = load_tokenizer(tokenizer_id)
    except Exception as exc:
        raise UsageError(f"could not load tokenizer {args.tokenizer!r}: {exc}") from exc

    fatal = args.fail_on
    tally = RunTally()

    for entry in entries:
        schema_ok = check_schema(entry.schema)
        if not schema_ok:
            tally.schemas_skipped += 1
            tally.skips.append(f"{entry.source}: {schema_ok.reason}")
            continue
        tally.schemas_checked += 1
        run_completeness(tally, engine, entry, tokenizer_id, args)
        run_soundness(tally, engine, entry, tokenizer_id, args)

    version = engine_version(args.engine)
    _print_summary(out, args, tally, entries, version, tokenizer_id, fatal)
    _print_blocks(out, tally, version, tokenizer)

    return EXIT_VIOLATION if tally.occurrences(fatal) else EXIT_OK


def _print_summary(out, args, tally, entries, version, tokenizer_id, fatal) -> None:
    print("maskcheck verify", file=out)
    print(f"  engine            {args.engine} {version}", file=out)
    print(f"  tokenizer         {tokenizer_id}", file=out)
    print(f"  schemas           {len(entries)} from {args.schemas}", file=out)
    print(f"  fatal properties  {', '.join(fatal) if fatal else 'none'}", file=out)
    print("", file=out)
    print(f"  schemas checked   {tally.schemas_checked}", file=out)
    print(f"  schemas skipped   {tally.schemas_skipped}", file=out)
    for name in PROPERTIES:
        stats = tally.tally(name)
        line = (
            f"  {name.ljust(16)}  {_plural(stats.checks, 'check')}, "
            f"{stats.skipped} skipped, {_plural(len(stats.violations), 'violation')}"
        )
        if stats.inconclusive:
            line += f", {stats.inconclusive} inconclusive"
        print(line, file=out)

    if any(tally.tally(name).inconclusive for name in PROPERTIES):
        print("", file=out)
        print(
            "  Inconclusive results ran but could not be judged: the walk hit the\n"
            "  token budget before completing a document, or its tokens split a\n"
            "  multi-byte character so the output is not text. Raise --max-steps to\n"
            "  convert the first kind into real checks.",
            file=out,
        )

    if tally.skips:
        print("", file=out)
        print("Skipped", file=out)
        for note in tally.skips:
            print(f"  {note}", file=out)


def _print_blocks(out, tally, version, tokenizer) -> None:
    occurrences = tally.all_occurrences
    if not occurrences:
        print("", file=out)
        print("No violations found.", file=out)
        return

    groups = group_by_cause(occurrences)
    print("", file=out)
    print(
        f"{_plural(len(occurrences), 'violation')} from "
        f"{_plural(len(groups), 'distinct cause')}.",
        file=out,
    )
    for index, group in enumerate(groups, start=1):
        print("", file=out)
        print(
            render_block(
                group,
                index=index,
                total=len(groups),
                engine_version=version,
                decode=lambda ids: tokenizer.decode(list(ids)),
            ),
            file=out,
        )


def _fail_on(value: str) -> tuple[str, ...]:
    if value.strip().lower() == "none":
        return ()
    chosen = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = [name for name in chosen if name not in PROPERTIES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown property {unknown[0]!r}; choose from {', '.join(PROPERTIES)} or none"
        )
    return chosen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maskcheck",
        description=(
            "Check a constrained-decoding engine against your own JSON Schemas. "
            "Completeness asks whether every valid document can still be produced; "
            "soundness asks whether everything the engine produces is valid."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser(
        "verify", help="run completeness and soundness against your schemas"
    )
    verify_parser.add_argument(
        "--engine",
        required=True,
        help=f"engine to test, one of: {', '.join(ENGINE_NAMES)}",
    )
    verify_parser.add_argument(
        "--tokenizer",
        required=True,
        help="Hugging Face tokenizer id, or a pinned short id (gpt2, qwen2.5, mistral, llama3)",
    )
    verify_parser.add_argument(
        "--schemas",
        required=True,
        help="a schema file, a directory searched for *.json, or a glob",
    )
    verify_parser.add_argument(
        "--revision",
        default=None,
        help="pin the tokenizer to a Hugging Face revision (default: repository default)",
    )
    verify_parser.add_argument(
        "--instances",
        type=int,
        default=10,
        help="valid documents generated per schema for completeness (default: 10)",
    )
    verify_parser.add_argument(
        "--walks",
        type=int,
        default=25,
        help="random walks per schema for soundness (default: 25)",
    )
    verify_parser.add_argument(
        "--max-steps",
        type=int,
        default=64,
        help="token budget for one soundness walk (default: 64)",
    )
    verify_parser.add_argument(
        "--seed", type=int, default=0, help="seed for generation and walks (default: 0)"
    )
    verify_parser.add_argument(
        "--fail-on",
        type=_fail_on,
        default=PROPERTIES,
        help=(
            "comma separated properties that make the run fail, or none "
            f"(default: {','.join(PROPERTIES)})"
        ),
    )
    return parser


def main(argv: list[str] | None = None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        return verify(args, out)
    except UsageError as exc:
        print(f"maskcheck: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("maskcheck: interrupted", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
