"""xgrammar completeness violation: numbers with a zero fractional part are
unreachable for {"type": "integer"}

JSON Schema draft 6 and later define "integer" as "matches any number with a zero
fractional part", explicitly including forms written with a decimal point or an
exponent. So `1.0`, `0.0` and `1e2` all validate against {"type": "integer"}.
xgrammar's integer grammar accepts only `-?(0|[1-9][0-9]*)`, so none of them can be
generated.

Confidence note: unlike finding 001 (`-0`, which is an integer under any reading),
this one depends on the draft-6+ definition of "integer". An engine targeting the
draft-4 reading ("no decimal point") would be correct to reject these. It is reported
as a spec-conformance disagreement, not as an outright bug, and the right resolution
may be documentation rather than a grammar change.

Environment: xgrammar 0.2.3, jsonschema 4.26.0, Python 3.12, macOS arm64.
Run: python 002_xgrammar_integer_zero_fractional_part.py
"""

import json

import jsonschema
import xgrammar as xgr

SCHEMA = {"type": "integer"}
INSTANCES = ["1.0", "0.0", "1e2", "-1e2", "0e0"]

tokenizer_info = xgr.TokenizerInfo(["-", "0", "1", "x"], vocab_size=4)
compiler = xgr.GrammarCompiler(tokenizer_info)

print(f"{'literal':<8} {'jsonschema':<12} {'xgrammar'}")
for literal in INSTANCES:
    valid = jsonschema.Draft202012Validator(SCHEMA).is_valid(json.loads(literal))
    m = xgr.GrammarMatcher(compiler.compile_json_schema(SCHEMA))
    accepted = m.accept_string(literal) and m.is_completed()
    print(f"{literal:<8} {str(valid):<12} {accepted}")
    assert valid is True and accepted is False, "behaviour changed in this version"

# 1.5 is correctly rejected by both: its fractional part is not zero.
m = xgr.GrammarMatcher(compiler.compile_json_schema(SCHEMA))
print(f"{'1.5':<8} {str(jsonschema.Draft202012Validator(SCHEMA).is_valid(1.5)):<12} "
      f"{m.accept_string('1.5') and m.is_completed()}")

print("\nREPRODUCED: draft-6+ integers with a zero fractional part are unreachable")
