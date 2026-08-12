"""xgrammar completeness violation: `\\uXXXX` spellings of fixed strings are unreachable

JSON has more than one spelling for the same string: `"\\u0061"` and `"a"` are the
same string, and a parser must treat them identically. Wherever a schema pins a string
to a fixed value -- an object key in `properties`, an `enum` member, a `const` -- the
compiled grammar accepts only the literal spelling and rejects every escaped
equivalent.

Why this is more than pedantry: Python's `json.dumps` escapes non-ASCII by *default*
(`ensure_ascii=True`), so a very large share of the JSON on the public internet spells
`é` as `\\u00e9`. A model that learned that convention, asked for a schema with a
non-ASCII key or enum value, will emit the escaped form and be blocked mid-string with
no valid continuation.

Character-level, so tokenizer-independent.

Environment: xgrammar 0.2.3, jsonschema 4.26.0, Python 3.12, macOS arm64.
Run: python 005_xgrammar_escaped_fixed_strings.py
"""

import json

import jsonschema
import xgrammar as xgr

tokenizer_info = xgr.TokenizerInfo(["a", "b", "c", "d"], vocab_size=4)
compiler = xgr.GrammarCompiler(tokenizer_info)


def check(label, schema, plain, escaped):
    validator = jsonschema.Draft202012Validator(schema)
    # Both spellings parse to the identical Python object.
    assert json.loads(plain) == json.loads(escaped), "spellings must be equivalent"
    results = []
    for text in (plain, escaped):
        assert validator.is_valid(json.loads(text)), f"{text} should be valid"
        matcher = xgr.GrammarMatcher(compiler.compile_json_schema(schema))
        results.append(matcher.accept_string(text) and matcher.is_completed())
    print(f"{label:<26} {plain:<22} {str(results[0]):<8} {escaped:<24} {results[1]}")
    return results


def obj(props, required):
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


print(f"{'schema pins':<26} {'plain':<22} {'ok':<8} {'escaped':<24} ok")
cases = [
    check(
        "non-ASCII object key",
        obj({"é": {"type": "string"}}, ["é"]),
        '{"é":"x"}',
        '{"\\u00e9":"x"}',
    ),
    check(
        "ASCII object key",
        obj({"a": {"type": "string"}}, ["a"]),
        '{"a":"x"}',
        '{"\\u0061":"x"}',
    ),
    check(
        "enum member",
        obj({"v": {"enum": ["alpha"]}}, ["v"]),
        '{"v":"alpha"}',
        '{"v":"\\u0061lpha"}',
    ),
    check(
        "const value",
        obj({"v": {"const": "yes"}}, ["v"]),
        '{"v":"yes"}',
        '{"v":"\\u0079es"}',
    ),
]

assert all(plain and not escaped for plain, escaped in cases), "behaviour changed"
print("\nREPRODUCED: escaped spellings of schema-fixed strings are unreachable")
print("Note: Python's json.dumps emits the escaped form by default (ensure_ascii=True).")
