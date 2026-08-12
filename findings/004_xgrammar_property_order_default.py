"""xgrammar completeness gap: by default only one ordering of object properties is
reachable

JSON object members are unordered, and JSON Schema `properties` is a map, not a
sequence. Every permutation of an object's keys is an equally valid instance. By
default xgrammar's compiled grammar accepts only the order in which the properties
happen to be written in the schema, so for an object with n required properties,
n! - 1 of the n! valid spellings cannot be generated.

Status: this is a documented knob, not an outright bug -- `compile_json_schema` takes
`any_order=False` by default and `any_order=True` restores all orderings. It is filed
because it is the textbook example of what this project is looking for: a *silent*
completeness failure. Nothing errors, output is still valid, but the reachable
language is a strict subset of the schema's language and the output distribution is
skewed toward the schema author's declaration order. A caller who never reads the
`any_order` docs has no way to notice.

The cost of the safe default is also worth stating: `any_order=True` is reported by
the maintainers to be more expensive to compile, which is presumably why the fast
default was chosen.

Environment: xgrammar 0.2.3, Python 3.12, macOS arm64.
Run: python 004_xgrammar_property_order_default.py
"""

import itertools
import json

import jsonschema
import xgrammar as xgr

SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string"}, "b": {"type": "string"}, "c": {"type": "string"}},
    "required": ["a", "b", "c"],
    "additionalProperties": False,
}

tokenizer_info = xgr.TokenizerInfo(["a", "b", "c", "d"], vocab_size=4)
compiler = xgr.GrammarCompiler(tokenizer_info)
validator = jsonschema.Draft202012Validator(SCHEMA)


def accepts(text: str, **kwargs) -> bool:
    matcher = xgr.GrammarMatcher(compiler.compile_json_schema(SCHEMA, **kwargs))
    return matcher.accept_string(text) and matcher.is_completed()


orderings = ["{" + ",".join(f'"{k}":"1"' for k in perm) + "}" for perm in itertools.permutations("abc")]

print(f"{'instance':<34} {'jsonschema':<12} {'default':<9} any_order=True")
default_ok = any_order_ok = 0
for text in orderings:
    valid = validator.is_valid(json.loads(text))
    d = accepts(text)
    a = accepts(text, any_order=True)
    default_ok += d
    any_order_ok += a
    assert valid, "every permutation must be valid"
    print(f"{text:<34} {str(valid):<12} {str(d):<9} {a}")

print(f"\nreachable by default:      {default_ok}/6")
print(f"reachable with any_order:  {any_order_ok}/6")

assert default_ok == 1 and any_order_ok == 6, "behaviour changed in this version"
print("\nREPRODUCED: 5 of 6 valid orderings are unreachable under default settings")
