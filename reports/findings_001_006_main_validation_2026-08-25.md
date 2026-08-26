# Findings 001-006 stable and current-main validation

Date: 2026-08-25

## Thesis

Each standalone reproducer must still distinguish a JSON or JSON Schema valid
input from XGrammar's accepted language on the exact current `main` revision.
An upstream test pass is only a compatibility control: it does not invalidate a
finding reproduced by an input absent from that suite.

The duplicate and related-work search is recorded separately in
[findings_001_006_upstream_audit_2026-08-25.md](findings_001_006_upstream_audit_2026-08-25.md).

## Exact revisions and environments

The latest stable release was installed from its published wheel. The official
repository was then cloned recursively and checked out at current `main`:


| Source                                                                            | Revision                                                                                                                         |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| [Latest official release](https://github.com/mlc-ai/xgrammar/releases/tag/v0.2.5) | `xgrammar==0.2.5`, published 2026-07-22                                                                                          |
| [`mlc-ai/xgrammar`](https://github.com/mlc-ai/xgrammar)                           | [`53da3ff8c0db359ecb6d4b41f154308c82a89aaf`](https://github.com/mlc-ai/xgrammar/commit/53da3ff8c0db359ecb6d4b41f154308c82a89aaf) |


Both ran in isolated CPython 3.10.20 environments. The `main` revision was built
from source using the repository's documented `scikit-build-core` procedure.
The oracle was `jsonschema 4.26.0` with `Draft202012Validator`. Every reproducer
used its own four-entry custom vocabulary, so no model or external tokenizer was
involved.

No upstream branch, issue, pull request, or comment was modified.

## Specification controls

The classifications use the following primary sources:

- [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259) permits a minus before zero,
includes exponent syntax in JSON numbers, includes CR in JSON whitespace,
defines objects as unordered, and permits any string character to use a
`\uXXXX` escape.
- [JSON Schema 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation#name-type)
defines `integer` as any number with a zero fractional part.
- [JSON Schema 2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core#section-4.2.2)
compares numbers by mathematical value and strings by code points, treats
object properties as unordered, and makes serialization differences
insignificant.

## Results

All six scripts exited zero and printed their `REPRODUCED` marker in both
environments.


| Finding | Stable 0.2.5 | Current `main` | Exact observed result and verdict                                                                                                                                                                                         |
| ------- | ------------ | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 001     | Reproduced   | Reproduced     | `-0` valid as an integer; XGrammar rejected it while accepting `0`, `-1`, and `-10`. Unambiguous completeness gap.                                                                                                        |
| 002     | Reproduced   | Reproduced     | `1.0`, `0.0`, `1e2`, `-1e2`, and `0e0` validated as integers and were all rejected. Valid under Draft 6 and later; disclosure must state the target dialect.                                                              |
| 003     | Reproduced   | Reproduced     | Space, tab, and LF were accepted as structural whitespace; CR was rejected at all four tested object positions and CRLF output was unreachable. Unambiguous completeness gap.                                             |
| 004     | Reproduced   | Reproduced     | Default mode accepted 1 of 6 property permutations; `any_order=True` accepted 6 of 6. This is now an explicit documented default with an opt-in relaxation.                                                               |
| 005     | Reproduced   | Reproduced     | Literal fixed keys, `enum`, and `const` values were accepted; all four equivalent `\uXXXX` spellings were rejected. Unambiguous completeness gap.                                                                         |
| 006     | Reproduced   | Reproduced     | Five exponent spellings of values in `[10, 20]` were rejected; plain `10`, `15`, and `20` were accepted and four out-of-range controls were rejected. Completeness gap with no observed soundness failure in this matrix. |


Verdict: none of findings 001-006 was fixed by current `main` at the tested
revision. Finding 004 should not be presented as an undisclosed bug. Finding 002
remains specification-dependent only in the sense that XGrammar does not declare
a JSON Schema dialect; its witnesses are integers under Draft 6 and later.

## Upstream suite control

The affected upstream test file passed in the exact source-built environment:

```text
518 passed in 4.60s
```

Command:

```text
python -m pytest tests/python/test_json_schema_converter.py -q
```

This shows that the six reproductions coexist with the current converter suite;
it is not evidence against them.

## Upstream disposition

All access to the official XGrammar repository was read-only. No issue or pull
request was drafted, opened, edited, or commented on.
