"""XGrammar accepts text that is not valid JSON on constrained string paths.

Length bounds reproduce for string values and property names. A one-character
pattern reproduces for string values. The behavior appears through both matcher
interfaces and with a three-entry vocabulary, so no external tokenizer is needed.

Environment: xgrammar 0.2.4 and 0.2.5, macOS arm64.
Run: python 007_xgrammar_constrained_string_characters.py
"""

import json

import xgrammar as xgr


def observed(schema, pieces):
    text = "".join(pieces)
    try:
        json.loads(text)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("the example must remain invalid JSON")

    compiler = xgr.GrammarCompiler(xgr.TokenizerInfo(pieces, vocab_size=3))
    compiled = compiler.compile_json_schema(schema)

    string_matcher = xgr.GrammarMatcher(compiled)
    by_string = string_matcher.accept_string(text) and string_matcher.is_completed()

    token_matcher = xgr.GrammarMatcher(compiled)
    steps = [token_matcher.accept_token(token_id) for token_id in range(3)]
    by_token = all(steps) and token_matcher.is_completed()
    return by_string, by_token


character = chr(0x1B)
cases = [
    (
        "bounded value",
        {"type": "string", "minLength": 1, "maxLength": 1},
        ['"', character, '"'],
    ),
    (
        "pattern value",
        {"type": "string", "pattern": "^.$"},
        ['"', character, '"'],
    ),
    (
        "bounded property name",
        {
            "type": "object",
            "propertyNames": {"minLength": 1, "maxLength": 1},
            "additionalProperties": {"type": "null"},
        },
        ['{"', character, '":null}'],
    ),
]

for label, schema, pieces in cases:
    by_string, by_token = observed(schema, pieces)
    print(f"{label}: accept_string={by_string}, accept_token={by_token}")
    assert by_string and by_token, "behavior changed in this version"

print("REPRODUCED: constrained strings can complete with invalid JSON text")
