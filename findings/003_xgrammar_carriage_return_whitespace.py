"""xgrammar completeness violation: carriage return is not accepted as JSON whitespace

RFC 8259 section 2 defines insignificant whitespace as exactly four characters:
space (%x20), horizontal tab (%x09), line feed (%x0A) and carriage return (%x0D).
xgrammar accepts the first three between structural elements and rejects the fourth,
at every position.

This is the most consequential finding in this batch. Any output formatted with CRLF
line endings is unreachable: a model asked for pretty-printed JSON that emits Windows
line endings will be blocked at the first newline, mid-generation, with no valid
continuation. Unlike the `-0` case this is text models really do produce.

Character-level, so tokenizer-independent.

Environment: xgrammar 0.2.3, Python 3.12, macOS arm64.
Run: python 003_xgrammar_carriage_return_whitespace.py
"""

import json

import xgrammar as xgr

SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string"}},
    "required": ["a"],
    "additionalProperties": False,
}

tokenizer_info = xgr.TokenizerInfo(["a", "b", "c", "d"], vocab_size=4)
compiler = xgr.GrammarCompiler(tokenizer_info)


def xgrammar_accepts(text: str) -> bool:
    matcher = xgr.GrammarMatcher(compiler.compile_json_schema(SCHEMA))
    return matcher.accept_string(text) and matcher.is_completed()


print("The four RFC 8259 whitespace characters, used between ':' and the value:\n")
print(f"{'whitespace':<14} {'json.loads':<12} {'xgrammar'}")
results = {}
for name, ws in [("space", " "), ("tab \\t", "\t"), ("LF \\n", "\n"), ("CR \\r", "\r")]:
    text = '{"a":%s"x"}' % ws
    try:
        json.loads(text)
        parses = True
    except json.JSONDecodeError:
        parses = False
    accepted = xgrammar_accepts(text)
    results[name] = accepted
    flag = "   <-- DISAGREE" if parses != accepted else ""
    print(f"{name:<14} {str(parses):<12} {accepted}{flag}")

assert results["space"] and results["tab \\t"] and results["LF \\n"]
assert not results["CR \\r"], "bug appears to be fixed in this version"

print("\nCR is rejected at every structural position:")
for label, text in [
    ("after {", '{\r"a":"x"}'),
    ("before :", '{"a"\r:"x"}'),
    ("after :", '{"a":\r"x"}'),
    ("before }", '{"a":"x"\r}'),
]:
    json.loads(text)  # all of these are valid JSON
    print(f"  {label:<10} xgrammar={xgrammar_accepts(text)}")

print("\nPractical consequence -- CRLF pretty-printed output is unreachable:")
crlf = '{\r\n  "a": "x"\r\n}'
lf = '{\n  "a": "x"\n}'
print(f"  LF   version accepted: {xgrammar_accepts(lf)}")
print(f"  CRLF version accepted: {xgrammar_accepts(crlf)}")

print("\nREPRODUCED: CR is not treated as JSON whitespace")
