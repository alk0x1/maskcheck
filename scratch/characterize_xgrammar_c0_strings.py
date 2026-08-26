"""Characterize XGrammar accepting raw C0 controls in constrained JSON strings.

This is a one-process grid sweep. It loads each registered Hugging Face tokenizer
once, builds one compiler for it, and reuses both across every C0 code point and
schema. It also runs tokenizer-independent value and property-name grids using
three-token custom vocabularies.

Run:
    uv run python scratch/characterize_xgrammar_c0_strings.py
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib.metadata import version
from typing import Iterable

import xgrammar as xgr

from fuzzer.tokenizers import REGISTRY, load_tokenizer


@dataclass(frozen=True)
class Case:
    label: str
    schema: dict


@dataclass(frozen=True)
class Outcome:
    accept_string: bool | None
    accept_token: bool | None
    error: str | None = None

    @property
    def cell(self) -> str:
        if self.error is not None:
            return "E/E"
        return "/".join(
            "A" if accepted else "R"
            for accepted in (self.accept_string, self.accept_token)
        )


@dataclass(frozen=True)
class CompilerContext:
    label: str
    compiler: xgr.GrammarCompiler
    encode: object


STRING_CASES = (
    Case("none", {"type": "string"}),
    Case("min=0", {"type": "string", "minLength": 0}),
    Case("min=1", {"type": "string", "minLength": 1}),
    Case("min=2", {"type": "string", "minLength": 2}),
    Case("max=0", {"type": "string", "maxLength": 0}),
    Case("max=1", {"type": "string", "maxLength": 1}),
    Case("max=2", {"type": "string", "maxLength": 2}),
    Case("both=0:0", {"type": "string", "minLength": 0, "maxLength": 0}),
    Case("both=0:1", {"type": "string", "minLength": 0, "maxLength": 1}),
    Case("both=1:1", {"type": "string", "minLength": 1, "maxLength": 1}),
    Case("both=1:2", {"type": "string", "minLength": 1, "maxLength": 2}),
    Case("both=2:2", {"type": "string", "minLength": 2, "maxLength": 2}),
    Case("pattern=''", {"type": "string", "pattern": ""}),
    Case("pattern=^.$", {"type": "string", "pattern": "^.$"}),
    Case("format=email", {"type": "string", "format": "email"}),
)


def property_names_schema(constraint: dict | None) -> dict:
    schema = {
        "type": "object",
        "additionalProperties": {"type": "null"},
    }
    if constraint is not None:
        schema["propertyNames"] = constraint
    return schema


PROPERTY_NAME_CASES = (
    Case("none", property_names_schema(None)),
    Case("min=0", property_names_schema({"minLength": 0})),
    Case("min=1", property_names_schema({"minLength": 1})),
    Case("min=2", property_names_schema({"minLength": 2})),
    Case("max=0", property_names_schema({"maxLength": 0})),
    Case("max=1", property_names_schema({"maxLength": 1})),
    Case("max=2", property_names_schema({"maxLength": 2})),
    Case("both=0:0", property_names_schema({"minLength": 0, "maxLength": 0})),
    Case("both=0:1", property_names_schema({"minLength": 0, "maxLength": 1})),
    Case("both=1:1", property_names_schema({"minLength": 1, "maxLength": 1})),
    Case("both=1:2", property_names_schema({"minLength": 1, "maxLength": 2})),
    Case("both=2:2", property_names_schema({"minLength": 2, "maxLength": 2})),
)


def completed_by_string(compiled: xgr.CompiledGrammar, text: str) -> bool:
    matcher = xgr.GrammarMatcher(compiled)
    return matcher.accept_string(text) and matcher.is_completed()


def completed_by_tokens(
    compiled: xgr.CompiledGrammar, token_ids: Iterable[int]
) -> bool:
    matcher = xgr.GrammarMatcher(compiled)
    for token_id in token_ids:
        if not matcher.accept_token(token_id):
            return False
    return matcher.is_completed()


def compile_cases(
    compiler: xgr.GrammarCompiler, cases: tuple[Case, ...]
) -> dict[str, xgr.CompiledGrammar | Exception]:
    compiled = {}
    for case in cases:
        try:
            compiled[case.label] = compiler.compile_json_schema(case.schema)
        except Exception as exc:
            compiled[case.label] = exc
    return compiled


def run_grid(
    cases: tuple[Case, ...],
    texts: dict[int, str],
    compiler: xgr.GrammarCompiler,
    encode,
) -> dict[int, dict[str, Outcome]]:
    compiled_cases = compile_cases(compiler, cases)
    output = {}
    for codepoint, text in texts.items():
        assert json.loads(text, strict=False) is not None
        try:
            json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            raise AssertionError(f"raw U+{codepoint:04X} unexpectedly parsed as JSON")

        encoded = encode(text)
        row = {}
        for case in cases:
            compiled = compiled_cases[case.label]
            if isinstance(compiled, Exception):
                row[case.label] = Outcome(None, None, repr(compiled))
                continue
            row[case.label] = Outcome(
                accept_string=completed_by_string(compiled, text),
                accept_token=completed_by_tokens(compiled, encoded),
            )
        output[codepoint] = row
    return output


def print_table(
    title: str,
    cases: tuple[Case, ...],
    results: dict[int, dict[str, Outcome]],
) -> None:
    print(f"## {title}\n")
    print("| C0 | " + " | ".join(case.label for case in cases) + " |")
    print("|---|" + "---|" * len(cases))
    for codepoint, row in results.items():
        print(
            f"| U+{codepoint:04X} | "
            + " | ".join(row[case.label].cell for case in cases)
            + " |"
        )
    print()

    print("Accepted raw C0 code points by column:\n")
    print("| Column | accept_string | accept_token |")
    print("|---|---|---|")
    for case in cases:
        string_points = [
            f"U+{codepoint:04X}"
            for codepoint, row in results.items()
            if row[case.label].accept_string
        ]
        token_points = [
            f"U+{codepoint:04X}"
            for codepoint, row in results.items()
            if row[case.label].accept_token
        ]
        print(
            f"| {case.label} | {', '.join(string_points) or 'none'} | "
            f"{', '.join(token_points) or 'none'} |"
        )
    print()

    print("Excluded labeled code points by column:\n")
    print("| Column | accept_string | accept_token |")
    print("|---|---|---|")
    for case in cases:
        string_points = [
            f"U+{codepoint:04X}"
            for codepoint, row in results.items()
            if row[case.label].accept_string is False
        ]
        token_points = [
            f"U+{codepoint:04X}"
            for codepoint, row in results.items()
            if row[case.label].accept_token is False
        ]
        print(
            f"| {case.label} | {', '.join(string_points) or 'none'} | "
            f"{', '.join(token_points) or 'none'} |"
        )
    print()

    errors = {
        (case.label, outcome.error)
        for row in results.values()
        for case in cases
        if (outcome := row[case.label]).error is not None
    }
    if errors:
        print("Compilation errors:\n")
        for label, error in sorted(errors):
            print(f"- {label}: `{error}`")
        print()


def real_contexts() -> list[CompilerContext]:
    tokenizers = {short_id: load_tokenizer(short_id) for short_id in REGISTRY}
    contexts = []
    for short_id, tokenizer in tokenizers.items():
        info = xgr.TokenizerInfo.from_huggingface(
            tokenizer.hf, vocab_size=tokenizer.vocab_size
        )
        contexts.append(
            CompilerContext(
                label=short_id,
                compiler=xgr.GrammarCompiler(info),
                encode=tokenizer.encode,
            )
        )
    assert len(tokenizers) == len(REGISTRY) == len(contexts)
    return contexts


def custom_grid(
    cases: tuple[Case, ...],
    texts: dict[int, str],
    vocabulary,
) -> dict[int, dict[str, Outcome]]:
    output = {}
    for codepoint, text in texts.items():
        vocab = vocabulary(chr(codepoint))
        assert len(vocab) == 3
        compiler = xgr.GrammarCompiler(xgr.TokenizerInfo(vocab, vocab_size=3))
        output.update(run_grid(cases, {codepoint: text}, compiler, lambda _: [0, 1, 2]))
    return output


def main() -> None:
    value_texts = {codepoint: f'"{chr(codepoint)}"' for codepoint in range(0x20)}
    key_texts = {
        codepoint: f'{{"{chr(codepoint)}":null}}' for codepoint in range(0x20)
    }

    print("# XGrammar raw C0 constrained-string characterization\n")
    print(f"- process id: {os.getpid()}")
    print(f"- xgrammar version: {version('xgrammar')}")
    if source_ref := os.environ.get("XGRAMMAR_SOURCE_REF"):
        print(f"- xgrammar source ref: {source_ref}")
    print(f"- registered tokenizers loaded once at startup: {', '.join(REGISTRY)}")
    print("- cell notation: `accept_string/accept_token`, `A` accepted, `R` rejected")
    print("- `E/E` means schema compilation failed and is listed below its table")
    print("- every tested text is rejected by strict `json.loads` before XGrammar runs\n")

    contexts = real_contexts()
    for context in contexts:
        print_table(
            f"String values, {context.label}",
            STRING_CASES,
            run_grid(STRING_CASES, value_texts, context.compiler, context.encode),
        )
        print_table(
            f"Property names, {context.label}",
            PROPERTY_NAME_CASES,
            run_grid(
                PROPERTY_NAME_CASES, key_texts, context.compiler, context.encode
            ),
        )

    print_table(
        "String values, custom three-token vocabulary",
        STRING_CASES,
        custom_grid(
            STRING_CASES,
            value_texts,
            lambda control: ['"', control, '"'],
        ),
    )
    print_table(
        "Property names, custom three-token vocabulary",
        PROPERTY_NAME_CASES,
        custom_grid(
            PROPERTY_NAME_CASES,
            key_texts,
            lambda control: ['{"', control, '":null}'],
        ),
    )


if __name__ == "__main__":
    main()
