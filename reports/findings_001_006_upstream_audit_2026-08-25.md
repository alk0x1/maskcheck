# Findings 001-006 upstream audit

Search date: 2026-08-25

Scope: issues, pull requests, commits, code, and documentation in the official
[`mlc-ai/xgrammar`](https://github.com/mlc-ai/xgrammar) repository. The issue and
pull-request search included open and closed items. Current-source statements
refer to `main` at
[`53da3ff8c0db359ecb6d4b41f154308c82a89aaf`](https://github.com/mlc-ai/xgrammar/commit/53da3ff8c0db359ecb6d4b41f154308c82a89aaf),
whose commit date is 2026-08-17. This audit did not execute that revision.
The separate runtime validation is recorded in
[findings_001_006_main_validation_2026-08-25.md](findings_001_006_main_validation_2026-08-25.md).

## Conclusion

| Finding | Upstream classification | Current disposition |
| --- | --- | --- |
| 001, integer `-0` | No exact report found | Related fixes cover `-0` only in the `number` and bounded-float paths. The integer production on current `main` still has `0` outside the optional-minus branch. |
| 002, zero-fraction/exponent integer spellings | No exact report found | Current code still emits only plain integer syntax. An official EBNF example permits an optional `.0`, so documentation and converter code are not aligned, but no issue or PR was found for this discrepancy. |
| 003, carriage return whitespace | No exact report found | Current code still defines arbitrary JSON whitespace as space, LF, or tab. A closed, unmerged PR explicitly recognized CR as valid JSON whitespace, but did not change `main`. |
| 004, default property order | **Exact prior report** | PR #474 reported the same order dependency. PR #668 later added `any_order`, while retaining and documenting declared order as the default. |
| 005, escaped spellings of fixed strings | No exact report found | Existing reports fix incorrect UTF-8 handling and required escaping of special property keys, not acceptance of all equivalent JSON spellings. Current fixed keys, `const`, and `enum` values remain single serialized byte strings. |
| 006, exponent spellings under numeric bounds | No exact minimum/maximum reproducer found; substantial related acknowledgement | PR #779 explicitly states that scientific notation remains outside the language for constrained numbers, but concerns `multipleOf` and was closed unmerged. Current bounded numbers still use a separate fixed-point range regex, while exponent syntax exists only in the unbounded branch. |

Only finding 004 is an exact duplicate. Findings 001, 002, 003, and 005 have
related upstream work but no matching report. Finding 006 is already acknowledged
upstream as a broader constrained-number limitation, but the search found no issue
or PR reproducing the specific `minimum`/`maximum` witness from the finding.

## Finding 001: integer negative zero

No issue or pull request was found that reports `-0` being unreachable for
`{"type":"integer"}`.

The current integer generator makes `"0"` one complete alternative and puts the
optional minus sign only before a nonzero first digit. That is the same production
shape measured by finding 001:
[`GenerateInteger`, lines 2227-2268](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L2227-L2268).

Related sources are not duplicates:

| Source | Status on 2026-08-25 | Relationship |
| --- | --- | --- |
| [PR #462: fix numbers `-0...`](https://github.com/mlc-ai/xgrammar/pull/462) | Merged 2025-11-02 as [`c1f156a1fa7174be24c9f6152bb8518ea86348a0`](https://github.com/mlc-ai/xgrammar/commit/c1f156a1fa7174be24c9f6152bb8518ea86348a0) | Fixes the unconstrained `number` production so forms such as `-0.123` are accepted. It does not change the `integer` production or cover the literal `-0`. |
| [Issue #662: cross-zero float ranges reject `-0.X`](https://github.com/mlc-ai/xgrammar/issues/662) | Closed 2026-06-26 | Bounded `number` ranges rejected negative fractions whose integer part is zero. The schema type, lexical witness, and range trigger differ from finding 001. |
| [PR #667: handle negative-zero float ranges](https://github.com/mlc-ai/xgrammar/pull/667) | Merged 2026-06-26 as [`e1d109dc8539ab5a9bb4416c0becb943af2b1cd9`](https://github.com/mlc-ai/xgrammar/commit/e1d109dc8539ab5a9bb4416c0becb943af2b1cd9) | Fixes #662 in `GenerateFloatRangeRegex`; it does not repair `GenerateInteger`. |

Classification: **no exact upstream correspondence; still represented in current
source**.

## Finding 002: integer values written with a decimal point or exponent

No issue or pull request was found for `1.0`, `0.0`, `1e2`, or equivalent JSON
number spellings being rejected by `{"type":"integer"}`.

Current `GenerateInteger` contains no fractional or exponent branch
([lines 2227-2268](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L2227-L2268)).
However, the official free-form JSON EBNF example defines `basic_integer` with an
optional `.0`
([documentation lines 635-641](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/docs/defining_structures/ebnf_grammar.md#L635-L641)).
That example still omits exponent spellings and is documentation, not the JSON
Schema converter implementation. It is evidence of an internal documentation/code
discrepancy, not an upstream bug report.

The negative-zero work in PRs #462 and #667 concerns `type: number`. PR #779
concerns decimal `multipleOf` and says scientific notation remains unsupported for
constrained numbers; neither addresses the JSON Schema meaning of `type: integer`.

Classification: **no exact upstream correspondence; current code and official
documentation disagree on the `.0` subset**.

## Finding 003: carriage return omitted from JSON whitespace

No issue or pull request was found that reports CR (`U+000D`) or CRLF JSON being
rejected by the JSON Schema converter.

The omission is explicit on current `main`: both the printable whitespace pattern
and the native character-class expression contain only space, LF, and tab
([lines 1988-2000](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L1988-L2000)).

| Source | Status on 2026-08-25 | Relationship |
| --- | --- | --- |
| [PR #123: allow unconstrained whitespace](https://github.com/mlc-ai/xgrammar/pull/123) | Merged 2024-12-07 as [`7cc2814389925c7a3d98730304e63aa39169cf1d`](https://github.com/mlc-ai/xgrammar/commit/7cc2814389925c7a3d98730304e63aa39169cf1d) | Introduced `any_whitespace=True`; it is the historical source of this path, but its report does not mention CR or CRLF. |
| [PR #780: custom JSON Schema whitespace patterns](https://github.com/mlc-ai/xgrammar/pull/780) | Closed without merge 2026-08-03; implementation commit [`f6a474660d333b23be5e319e019d5af71bedffde`](https://github.com/mlc-ai/xgrammar/commit/f6a474660d333b23be5e319e019d5af71bedffde) | Its validator explicitly treats space, tab, LF, and CR as the allowed JSON whitespace characters. It would permit a caller-supplied CR-inclusive pattern, but it does not report or repair the CR omission in the default pattern and is absent from `main`. |
| [Issue #345: customize the whitespace pattern](https://github.com/mlc-ai/xgrammar/issues/345) | Closed 2025-06-30 | Asks how to limit repeated newlines. It is about whitespace quantity/configuration, not CR conformance. |

Classification: **no exact upstream correspondence; a closed feature PR recognizes
the four-character JSON set, while current default code still omits CR**.

## Finding 004: declared property order by default

This finding has an exact prior upstream report.

[PR #474](https://github.com/mlc-ai/xgrammar/pull/474), opened 2025-11-13,
states that JSON Schema conversion has an internal order dependency and demonstrates
that a later property cannot be generated before an earlier property. This is the
same behavioral claim as finding 004. Its permutation implementation
([`863b328140050387a9d9f1fc64452b3480a6756c`](https://github.com/mlc-ai/xgrammar/commit/863b328140050387a9d9f1fc64452b3480a6756c))
was closed without merge on 2026-01-03 because the proposed grammar grew
factorially and the change was not planned.

[PR #668](https://github.com/mlc-ai/xgrammar/pull/668) later added the `any_order`
option and merged on 2026-06-23 as
[`24ed4e640ce76897224ef11fd11f3b8f0144d982`](https://github.com/mlc-ai/xgrammar/commit/24ed4e640ce76897224ef11fd11f3b8f0144d982).
Its description explicitly says that `False`, the default, requires declared order,
while `True` permits either order. Current API documentation retains
`any_order=False`
([Python API lines 239-250](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/python/xgrammar/grammar.py#L239-L250))
and the structural-tag documentation repeats that declared order is the default
([lines 203-221](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/docs/structural_tag/structural_tag.md#L203-L221)).

Classification: **exact duplicate of PR #474; now an explicit documented default
with an opt-in relaxation, not an unreported bug**.

## Finding 005: escaped spellings of fixed strings

No issue or pull request was found that reports equivalent `\uXXXX` spellings being
unreachable for ordinary fixed property keys, string `enum` members, or string
`const` values.

Current code explains the behavior. Property keys are serialized once and inserted
as one byte string
([lines 2456-2469](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L2456-L2469)).
`const` and `enum` values are likewise serialized once
([lines 1415-1433](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L1415-L1433))
and emitted as exact `ByteString` alternatives
([lines 3069-3081](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L3069-L3081)).
No alternative JSON escape spellings are generated in these paths.

Related upstream reports are narrower and not duplicates:

| Source | Status on 2026-08-25 | Why it differs |
| --- | --- | --- |
| [Issue #418: Chinese enum values misinterpreted as Latin-1](https://github.com/mlc-ai/xgrammar/issues/418) | Closed 2025-09-10 | A serialization regression made the intended literal Unicode value itself unreachable. It does not ask the grammar to accept both literal and `\uXXXX` spellings. |
| [PR #419: fix UTF-8 matching in enum and const](https://github.com/mlc-ai/xgrammar/pull/419) | Merged 2025-09-10 as [`8e2ddee4993e09d56b3cfa6d918c4e723742a9d9`](https://github.com/mlc-ai/xgrammar/commit/8e2ddee4993e09d56b3cfa6d918c4e723742a9d9) | Repairs #418's UTF-8/Latin-1 corruption. It restores the intended fixed literal, not all equivalent encodings. |
| [Issue #636: control character in a schema property key](https://github.com/mlc-ai/xgrammar/issues/636) | Closed 2026-06-10 | Reports that a key which *must* be escaped instead admitted a raw control byte and rejected its required escape. Finding 005 uses ordinary keys/values and asks for optional equivalent escape spellings. |
| [PR #655: escape JSON Schema property keys](https://github.com/mlc-ai/xgrammar/pull/655) | Merged 2026-06-10 as [`87b353d10f2dfcdf3fcc4efc54d05e1c2aa1e1fe`](https://github.com/mlc-ai/xgrammar/commit/87b353d10f2dfcdf3fcc4efc54d05e1c2aa1e1fe) | Serializes special fixed keys into one valid JSON spelling, fixing #636. It does not add alternate spellings for ordinary keys, enums, or consts. |
| [Issue #800](https://github.com/mlc-ai/xgrammar/issues/800), [PR #822](https://github.com/mlc-ai/xgrammar/pull/822), and [PR #828](https://github.com/mlc-ai/xgrammar/pull/828) | Issue and both PRs open | Concern the lost escape branch in `minLength`, `maxLength`, and `pattern` free-form string paths. They do not cover schema-fixed strings. |

Classification: **no exact upstream correspondence; existing Unicode and escaping
fixes address different failures**.

## Finding 006: exponent spellings under numeric bounds

No issue or pull request was found that reproduces `1e1` becoming unreachable when
only `minimum` and/or `maximum` is added.

Current source contains the exact architectural split: a bounded number immediately
returns `GenerateFloatRangeRegex(..., precision=6)`
([lines 2305-2326](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L2305-L2326)),
whereas the exponent production is constructed only after that return, in the
unbounded branch
([lines 2329-2350](https://github.com/mlc-ai/xgrammar/blob/53da3ff8c0db359ecb6d4b41f154308c82a89aaf/cpp/json_schema_converter.cc#L2329-L2350)).

| Source | Status on 2026-08-25 | Relationship |
| --- | --- | --- |
| [PR #661: correct number/integer range grammars](https://github.com/mlc-ai/xgrammar/pull/661) | Closed without merge 2026-07-01; head [`e34992ebcc529f404f44e44b7c934d1564b837e3`](https://github.com/mlc-ai/xgrammar/commit/e34992ebcc529f404f44e44b7c934d1564b837e3) | Reports both soundness and completeness defects in the same bounded-number regex generator, including unreachable `0.1` under `exclusiveMinimum: 0`. It does not mention exponent spellings. |
| [PR #669: fix number generation](https://github.com/mlc-ai/xgrammar/pull/669) | Merged 2026-06-26 as [`c1bc06c1db00b222125dcf54aa70100a38383066`](https://github.com/mlc-ai/xgrammar/commit/c1bc06c1db00b222125dcf54aa70100a38383066) | Superseded #661 and repaired its listed range errors, but retained the fixed-point range-regex design and did not add exponent syntax. |
| [Issue #662](https://github.com/mlc-ai/xgrammar/issues/662) and [PR #667](https://github.com/mlc-ai/xgrammar/pull/667) | Issue closed; PR merged 2026-06-26 | Another completeness defect in the same range generator, limited to `-0.X` across zero. It does not cover exponent notation. |
| [PR #779: decimal `multipleOf`](https://github.com/mlc-ai/xgrammar/pull/779) | Closed without merge 2026-08-03; implementation [`ec101eb5bd0c4120f525457f542d73e5471eb4fa`](https://github.com/mlc-ai/xgrammar/commit/ec101eb5bd0c4120f525457f542d73e5471eb4fa) | Its behavior section explicitly says scientific notation remains outside the generated language for constrained numbers. This is direct acknowledgement of the broader limitation, but the PR is about `multipleOf`, not a report of the minimum/maximum-only witness, and it did not land. |

Classification: **substantial related upstream acknowledgement, but no exact
minimum/maximum duplicate; the limitation remains visible in current source**.

## Search formulations

Repository-wide issue and pull-request searches used combinations of:

- `negative zero`, `-0`, `-0.123`, and `basic_integer`
- `1.0`, `0.0`, `1e2`, `zero fractional`, `decimal point`, and `integer exponent`
- `carriage return`, `CRLF`, `%x0D`, `\r`, `JSON whitespace`, and `whitespace_pattern`
- `property order`, `order dependency`, `permutation`, and `any_order`
- `unicode escape`, `\uXXXX`, `\u0061`, `escaped spelling`, `escaped property`, `enum`, and `const`
- `exponent notation`, `scientific notation`, `1e1`, `minimum`, `maximum`, `bounded`, and `range`

Search hits were followed into linked issues, superseding PRs, merged commits, and
the current converter implementation. Absence means no match was found under these
formulations in the official repository; it is not a proof that no differently
worded historical mention exists.

## Upstream disposition

No issue or pull request was drafted, opened, edited, or commented on during this
audit. All upstream activity was read-only.
