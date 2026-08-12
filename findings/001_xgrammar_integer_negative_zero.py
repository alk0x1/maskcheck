"""xgrammar completeness violation: `-0` is unreachable for {"type": "integer"}

The JSON literal `-0` is valid JSON, is written in plain integer syntax (no decimal
point, no exponent), and validates against {"type": "integer"} under every JSON Schema
draft. xgrammar's compiled grammar rejects it: after `-`, only the digits 1-9 are
allowed, so `0` can never follow a minus sign.

This is character-level, so it is tokenizer-independent and affects every vocabulary.

Impact is small in isolation -- models rarely emit `-0` -- but it is an unambiguous
conformance gap with a two-line repro, and it is the same off-by-one in the number
grammar that would matter more if it extended to `-0.5` (it does not; `{"type":
"number"}` handles every case correctly).

Environment: xgrammar 0.2.3, jsonschema 4.26.0, Python 3.12, macOS arm64.
Run: python 001_xgrammar_integer_negative_zero.py
"""

import json

import jsonschema
import xgrammar as xgr

SCHEMA = {"type": "integer"}
INSTANCE = "-0"

# The reference says this is valid.
jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(INSTANCE))
print(f"jsonschema: {INSTANCE!r} is valid against {SCHEMA}")

# A trivial 4-token vocabulary is enough; nothing here depends on the tokenizer.
tokenizer_info = xgr.TokenizerInfo(["-", "0", "1", "x"], vocab_size=4)
compiler = xgr.GrammarCompiler(tokenizer_info)
matcher = xgr.GrammarMatcher(compiler.compile_json_schema(SCHEMA))

accepted = matcher.accept_string(INSTANCE)
print(f"xgrammar:   accept_string({INSTANCE!r}) = {accepted}")

# expected: True
# actual:   False  -- `0` is not an allowed continuation of `-`
assert accepted is False, "bug appears to be fixed in this version"

# For contrast, these all work:
for literal in ["0", "-1", "-10"]:
    m = xgr.GrammarMatcher(compiler.compile_json_schema(SCHEMA))
    print(f"xgrammar:   accept_string({literal!r}) = {m.accept_string(literal)}")

print("\nREPRODUCED: -0 is unreachable for {'type': 'integer'}")
