"""The CLI contract: what a caller's own schemas get them, and what fails the run."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

from fuzzer.cli import (
    EXIT_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    UsageError,
    build_parser,
    discover_schemas,
    generate_instances,
    main,
)
from fuzzer.engines import registry

TOKENIZER = "gpt2"

# Property declaration order is significant to XGrammar by default, and the instance
# generator permutes keys, so this schema reliably produces a completeness violation.
ORDERED = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name", "age"],
    "additionalProperties": False,
}

CLEAN = {"type": "boolean"}


def write_schema(directory: Path, name: str, schema: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(schema))
    return path


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def test_discovery_reads_a_single_file(tmp_path):
    write_schema(tmp_path, "one.json", CLEAN)
    found = discover_schemas(str(tmp_path / "one.json"))
    assert [entry.schema for entry in found] == [CLEAN]


def test_discovery_walks_a_directory_in_sorted_order(tmp_path):
    write_schema(tmp_path, "b.json", CLEAN)
    write_schema(tmp_path, "a.json", ORDERED)
    nested = tmp_path / "nested"
    nested.mkdir()
    write_schema(nested, "c.json", CLEAN)
    found = discover_schemas(str(tmp_path))
    assert [Path(entry.source).name for entry in found] == ["a.json", "b.json", "c.json"]


def test_discovery_accepts_a_glob(tmp_path):
    write_schema(tmp_path, "keep.json", CLEAN)
    (tmp_path / "ignore.txt").write_text("not a schema")
    found = discover_schemas(str(tmp_path / "*.json"))
    assert len(found) == 1


def test_discovery_reports_an_empty_match_rather_than_running_nothing(tmp_path):
    with pytest.raises(UsageError, match="no schema files matched"):
        discover_schemas(str(tmp_path / "*.json"))


def test_discovery_names_the_file_it_could_not_parse(tmp_path):
    (tmp_path / "broken.json").write_text("{not json")
    with pytest.raises(UsageError, match="broken.json"):
        discover_schemas(str(tmp_path))


def test_discovery_rejects_a_file_that_is_not_one_schema_object(tmp_path):
    (tmp_path / "many.json").write_text("[{}, {}]")
    with pytest.raises(UsageError, match="one JSON Schema object per file"):
        discover_schemas(str(tmp_path))


def test_generated_documents_are_all_valid_against_the_schema():
    from fuzzer.oracle.validator import validate_text

    documents = generate_instances(ORDERED, count=6, seed=0)
    assert documents
    assert all(validate_text(ORDERED, text) for text in documents)


def test_unsatisfiable_schema_yields_no_documents_instead_of_invalid_ones():
    # The generator does not model "pattern", so anything it emits here would be
    # invalid. Returning nothing is what lets the CLI skip rather than misreport.
    assert generate_instances({"type": "string", "pattern": "^zzz$"}, count=4, seed=0) == []


def test_missing_engine_is_reported_with_an_install_hint(monkeypatch):
    broken = registry.EngineSpec(
        name="xgrammar",
        module="fuzzer.engines.does_not_exist",
        adapter="Missing",
        distribution="xgrammar",
        extra="xgrammar",
    )
    monkeypatch.setitem(registry.SPECS, "xgrammar", broken)
    with pytest.raises(registry.EngineUnavailable, match=r"pip install .*\[xgrammar\]"):
        registry.load_engine("xgrammar")
    assert registry.availability()["xgrammar"] is None


def test_unknown_engine_lists_what_is_available(tmp_path):
    write_schema(tmp_path, "a.json", CLEAN)
    code, _ = run(
        ["verify", "--engine", "nope", "--tokenizer", TOKENIZER, "--schemas", str(tmp_path)]
    )
    assert code == EXIT_ERROR


def test_fail_on_rejects_an_unknown_property():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["verify", "--engine", "xgrammar", "--tokenizer", "gpt2",
             "--schemas", ".", "--fail-on", "spelling"]
        )


def test_fail_on_defaults_to_both_properties():
    args = build_parser().parse_args(
        ["verify", "--engine", "xgrammar", "--tokenizer", "gpt2", "--schemas", "."]
    )
    assert args.fail_on == ("completeness", "soundness")


def test_fail_on_none_disarms_the_exit_code():
    args = build_parser().parse_args(
        ["verify", "--engine", "xgrammar", "--tokenizer", "gpt2",
         "--schemas", ".", "--fail-on", "none"]
    )
    assert args.fail_on == ()


def test_invalid_schema_is_skipped_and_named_not_crashed(tmp_path):
    write_schema(tmp_path, "bad.json", {"type": "not-a-type"})
    write_schema(tmp_path, "good.json", CLEAN)
    code, output = run(
        ["verify", "--engine", "xgrammar", "--tokenizer", TOKENIZER,
         "--schemas", str(tmp_path), "--instances", "2", "--walks", "2"]
    )
    assert code == EXIT_OK
    assert "schemas checked   1" in output
    assert "schemas skipped   1" in output
    assert "bad.json" in output


def test_clean_schema_passes_with_a_zero_exit(tmp_path):
    write_schema(tmp_path, "clean.json", CLEAN)
    code, output = run(
        ["verify", "--engine", "xgrammar", "--tokenizer", TOKENIZER,
         "--schemas", str(tmp_path), "--instances", "3", "--walks", "3"]
    )
    assert code == EXIT_OK
    assert "No violations found." in output


def test_violation_fails_the_run_and_prints_one_block_per_cause(tmp_path):
    write_schema(tmp_path, "ordered.json", ORDERED)
    code, output = run(
        ["verify", "--engine", "xgrammar", "--tokenizer", TOKENIZER,
         "--schemas", str(tmp_path), "--instances", "6", "--walks", "3"]
    )
    assert code == EXIT_VIOLATION
    declared = re.search(r"from (\d+) distinct cause", output)
    assert declared, output
    # Exactly one block per distinct cause, no more and no fewer.
    assert output.count("Cause ") == int(declared.group(1))
    assert "ordered.json" in output
    assert "witness document" in output


def test_fail_on_selects_which_property_is_fatal(tmp_path):
    write_schema(tmp_path, "ordered.json", ORDERED)
    argv = [
        "verify", "--engine", "xgrammar", "--tokenizer", TOKENIZER,
        "--schemas", str(tmp_path), "--instances", "6", "--walks", "3",
    ]
    fatal, _ = run(argv + ["--fail-on", "completeness"])
    ignored, output = run(argv + ["--fail-on", "soundness"])
    assert fatal == EXIT_VIOLATION
    # The violation is still reported, it just no longer decides the exit code.
    assert ignored == EXIT_OK
    assert "completeness violation" in output


def test_unloadable_tokenizer_is_a_usage_error_not_a_traceback(tmp_path):
    write_schema(tmp_path, "a.json", CLEAN)
    code, _ = run(
        ["verify", "--engine", "xgrammar", "--tokenizer", "no-such-org/no-such-tokenizer",
         "--schemas", str(tmp_path)]
    )
    assert code == EXIT_ERROR
