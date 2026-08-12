"""Handwritten suite of known-tricky schemas.

Biased toward constructs that stress token boundaries rather than toward broad JSON
Schema coverage. Every instance here is written the way a model would emit it, with no
incidental whitespace, because the canonical tokenization of the compact form is where
tokens straddle grammar elements.

Instances are asserted valid by the reference validator in the test suite. A case whose
instance is not actually valid tests nothing, so that guard is not optional.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Case:
    id: str
    schema: dict
    instances: tuple[str, ...]
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def _obj(props: dict, required: list[str] | None = None, extra: bool = False) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": extra,
    }


STR = {"type": "string"}

CORPUS: tuple[Case, ...] = (
    Case(
        id="single_string_field",
        schema=_obj({"a": STR}),
        instances=('{"a":"x"}',),
        note="M0 baseline. GPT-2 spells this with {\" and \":\" and \"} .",
        tags=("boundary",),
    ),
    Case(
        id="adjacent_short_keys",
        schema=_obj({"a": STR, "b": STR}),
        instances=('{"a":"x","b":"y"}',),
        note='The ","  between fields is a single token in most BPE vocabularies.',
        tags=("boundary",),
    ),
    Case(
        id="many_adjacent_keys",
        schema=_obj({"a": STR, "b": STR, "c": STR, "d": STR}),
        instances=('{"a":"1","b":"2","c":"3","d":"4"}',),
        note="More boundaries per instance, more chances to straddle.",
        tags=("boundary",),
    ),
    Case(
        id="empty_string_values",
        schema=_obj({"a": STR, "b": STR}),
        instances=('{"a":"","b":""}',),
        note='Empty strings make "" and "","  land as single tokens.',
        tags=("boundary",),
    ),
    Case(
        id="prefix_keys",
        schema=_obj({"a": STR, "ab": STR, "abc": STR}),
        instances=('{"a":"x","ab":"y","abc":"z"}',),
        note="Keys that are prefixes of each other stress key disambiguation.",
        tags=("prefix",),
    ),
    Case(
        id="enum_shared_prefix",
        schema=_obj({"v": {"enum": ["alpha", "alphabet", "alphabetical"]}}),
        instances=('{"v":"alpha"}', '{"v":"alphabet"}', '{"v":"alphabetical"}'),
        note="A shorter enum member is a proper prefix of a longer one.",
        tags=("prefix", "enum"),
    ),
    Case(
        id="const_value",
        schema=_obj({"v": {"const": "yes"}}),
        instances=('{"v":"yes"}',),
        tags=("enum",),
    ),
    Case(
        id="nested_objects",
        schema=_obj({"a": _obj({"b": _obj({"c": STR})})}),
        instances=('{"a":{"b":{"c":"d"}}}',),
        note='Closing run "}}} is a single token in several vocabularies.',
        tags=("boundary", "nesting"),
    ),
    Case(
        id="array_of_strings",
        schema=_obj({"a": {"type": "array", "items": STR}}),
        instances=('{"a":[]}', '{"a":["x"]}', '{"a":["x","y","z"]}'),
        note='["  and ","  and "]  all straddle grammar elements.',
        tags=("boundary", "array"),
    ),
    Case(
        id="array_of_objects",
        schema=_obj({"a": {"type": "array", "items": _obj({"b": STR})}}),
        instances=('{"a":[{"b":"x"},{"b":"y"}]}',),
        note='}, {" is a dense boundary region.',
        tags=("boundary", "array", "nesting"),
    ),
    Case(
        id="integers",
        schema=_obj({"n": {"type": "integer"}}),
        instances=('{"n":0}', '{"n":1}', '{"n":-1}', '{"n":42}', '{"n":-0}'),
        note="-0 is a legal JSON integer literal and a common edge case.",
        tags=("number",),
    ),
    Case(
        id="numbers_with_exponents",
        schema=_obj({"n": {"type": "number"}}),
        instances=(
            '{"n":0.5}',
            '{"n":-0.5}',
            '{"n":1e10}',
            '{"n":1E10}',
            '{"n":1e+10}',
            '{"n":1e-10}',
            '{"n":-1.5e-10}',
        ),
        note="Exponent forms are where number grammars most often disagree.",
        tags=("number",),
    ),
    Case(
        id="bounded_number",
        schema=_obj({"n": {"type": "integer", "minimum": 10, "maximum": 20}}),
        instances=('{"n":10}', '{"n":15}', '{"n":20}'),
        note="Numeric bounds are hard to express in a grammar; engines approximate.",
        tags=("number",),
    ),
    Case(
        id="booleans_and_null",
        schema=_obj({"a": {"type": "boolean"}, "b": {"type": "null"}}),
        instances=('{"a":true,"b":null}', '{"a":false,"b":null}'),
        tags=("literal",),
    ),
    Case(
        id="string_escapes",
        schema=_obj({"s": STR}),
        instances=(
            r'{"s":"a\nb"}',
            r'{"s":"a\"b"}',
            r'{"s":"a\\b"}',
            r'{"s":"a\/b"}',
            r'{"s":"a\tb"}',
            r'{"s":"é"}',
        ),
        note="Escape sequences are multi-character atoms that tokenizers split freely.",
        tags=("escape",),
    ),
    Case(
        id="unicode_values",
        schema=_obj({"s": STR}),
        instances=(
            '{"s":"é"}',
            '{"s":"日本語"}',
            '{"s":"emoji 🙂"}',
            '{"s":"mixed aé日🙂"}',
        ),
        note="Multi-byte characters split across tokens in byte-level BPE.",
        tags=("unicode",),
    ),
    Case(
        id="unicode_keys",
        schema=_obj({"é": STR, "日": STR}),
        instances=('{"é":"x","日":"y"}',),
        note="Non-ASCII keys, where the key itself spans several tokens.",
        tags=("unicode",),
    ),
    Case(
        id="optional_keys",
        schema={
            "type": "object",
            "properties": {"a": STR, "b": STR, "c": STR},
            "required": ["a"],
            "additionalProperties": False,
        },
        instances=(
            '{"a":"x"}',
            '{"a":"x","b":"y"}',
            '{"a":"x","c":"z"}',
            '{"a":"x","b":"y","c":"z"}',
        ),
        note="Optional keys multiply the legal continuations after every comma.",
        tags=("optional",),
    ),
    Case(
        id="anyof_shared_prefix",
        schema=_obj(
            {
                "v": {
                    "anyOf": [
                        {"const": "abcdef"},
                        {"const": "abcxyz"},
                        {"const": "abc"},
                    ]
                }
            }
        ),
        instances=('{"v":"abcdef"}', '{"v":"abcxyz"}', '{"v":"abc"}'),
        note="Branches share a long prefix, so the choice point is mid-token.",
        tags=("prefix", "anyof"),
    ),
    Case(
        id="anyof_types",
        schema=_obj({"v": {"anyOf": [{"type": "string"}, {"type": "integer"}]}}),
        instances=('{"v":"x"}', '{"v":7}'),
        tags=("anyof",),
    ),
    Case(
        id="recursive_ref",
        schema={
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {"v": STR, "next": {"$ref": "#/$defs/node"}},
                    "required": ["v"],
                    "additionalProperties": False,
                }
            },
            "$ref": "#/$defs/node",
        },
        instances=(
            '{"v":"a"}',
            '{"v":"a","next":{"v":"b"}}',
            '{"v":"a","next":{"v":"b","next":{"v":"c"}}}',
        ),
        note="Recursive $ref, the construct most likely to hit engine depth limits.",
        tags=("nesting", "ref"),
    ),
    Case(
        id="empty_object",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        instances=("{}",),
        note="{} is usually a single token.",
        tags=("boundary",),
    ),
    Case(
        id="whitespace_variants",
        schema=_obj({"a": STR}),
        instances=('{"a":"x"}', '{ "a": "x" }', '{\n  "a": "x"\n}'),
        note="Same document, different whitespace, all valid JSON.",
        tags=("whitespace",),
    ),
)

BY_ID: dict[str, Case] = {c.id: c for c in CORPUS}


def cases(*tags: str) -> tuple[Case, ...]:
    """Cases carrying every given tag (all cases when no tag is given)."""
    if not tags:
        return CORPUS
    return tuple(c for c in CORPUS if set(tags) <= set(c.tags))
