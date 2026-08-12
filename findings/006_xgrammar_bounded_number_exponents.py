"""xgrammar completeness violation: adding minimum/maximum makes exponent spellings
unreachable

`{"type": "number"}` on its own accepts exponent notation: `1e1` compiles and is
accepted. Add `minimum` and `maximum` and it stops: `1e1` is the number 10, sits
inside `[10, 20]`, and is rejected. So does every other spelling that reaches an
in-range value through an exponent or a shifted decimal point -- `2e1`, `0.1e2`,
`100e-1`, `1.5e1`.

This is distinct from finding 002 and stronger. 002 depends on the draft-6+ reading of
"integer"; this one uses `"type": "number"`, where `1e1` is a valid number under every
draft and no reading of the spec excludes it.

The engine is *sound* here -- `1e3` (1000) and `0.5` are both correctly rejected -- so
the bound is being enforced, just by narrowing the grammar to plain decimal literals
rather than by constraining the value.

Character-level, so tokenizer-independent.

Environment: xgrammar 0.2.3, jsonschema 4.26.0, Python 3.12, macOS arm64.
Run: python 006_xgrammar_bounded_number_exponents.py
"""

import json

import jsonschema
import xgrammar as xgr

tokenizer_info = xgr.TokenizerInfo(["a", "b", "c", "d"], vocab_size=4)
compiler = xgr.GrammarCompiler(tokenizer_info)


def accepts(schema, text):
    matcher = xgr.GrammarMatcher(compiler.compile_json_schema(schema))
    return matcher.accept_string(text) and matcher.is_completed()


UNBOUNDED = {"type": "number"}
BOUNDED = {"type": "number", "minimum": 10, "maximum": 20}

print("Exponent notation works until a bound is added:\n")
print(f"  1e1 with {UNBOUNDED}: {accepts(UNBOUNDED, '1e1')}")
print(f"  1e1 with {BOUNDED}: {accepts(BOUNDED, '1e1')}")
assert accepts(UNBOUNDED, "1e1"), "unbounded numbers should accept exponents"
assert not accepts(BOUNDED, "1e1"), "behaviour changed in this version"

validator = jsonschema.Draft202012Validator(BOUNDED)
print(f"\nEvery spelling of a value inside [10, 20], with {BOUNDED}:\n")
print(f"  {'literal':<10} {'value':<8} {'jsonschema':<12} {'xgrammar':<10} verdict")

unreachable = 0
for literal in ["10", "15", "20", "1e1", "2e1", "0.1e2", "100e-1", "1.5e1", "9", "21", "1e3", "0.5"]:
    value = json.loads(literal)
    valid = validator.is_valid(value)
    accepted = accepts(BOUNDED, literal)
    if valid and not accepted:
        verdict = "UNREACHABLE (completeness)"
        unreachable += 1
    elif not valid and accepted:
        verdict = "ACCEPTED BUT INVALID (soundness)"
    else:
        verdict = "agree"
    print(f"  {literal:<10} {value!s:<8} {str(valid):<12} {str(accepted):<10} {verdict}")

assert unreachable == 5, f"expected 5 unreachable spellings, got {unreachable}"
print(f"\nREPRODUCED: {unreachable} valid in-range spellings are unreachable once a bound is set")
print("No soundness violations: out-of-range values are correctly rejected.")
