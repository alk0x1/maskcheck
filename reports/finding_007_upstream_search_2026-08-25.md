# Finding 007 upstream duplicate search

Search date: 2026-08-25

Scope: issues and pull requests in the official
[`mlc-ai/xgrammar`](https://github.com/mlc-ai/xgrammar) repository. The search
included open and closed issues and open, closed, and merged pull requests. It
did not test or inspect the behavior of the current `main` branch.

## Conclusion

The `minLength` and `maxLength` portion of finding 007 is already covered
upstream. A new report limited to raw U+0000 through U+001F characters in
length-bounded strings would duplicate open issue
[#800](https://github.com/mlc-ai/xgrammar/issues/800). Two open pull requests,
[#822](https://github.com/mlc-ai/xgrammar/pull/822) and
[#828](https://github.com/mlc-ai/xgrammar/pull/828), explicitly repair the
same C0 admission in the length-constrained path.

Issue #800 also names `pattern` as an affected constrained-string path and
describes the same loss of the JSON-aware string production. It is therefore
a substantial overlap for the `pattern` result in finding 007, although its
reproduction demonstrates unreachable valid escapes rather than directly
asserting acceptance of every raw C0 character.

No equivalent report was found for the `propertyNames` result. Existing
`propertyNames` reports concern different converter defects.

## Direct coverage

| Source | Status on 2026-08-25 | Coverage of finding 007 |
| --- | --- | --- |
| [Issue #800: JSON Schema maxLength/minLength/pattern on strings drops the escape branch](https://github.com/mlc-ai/xgrammar/issues/800) | Open | Same constrained-string lowering. It reports that `minLength`, `maxLength`, and `pattern` replace the normal JSON string production. Its displayed bounded character class excludes only quote, backslash, U+000D, and U+000A, leaving the other C0 characters admissible. |
| [PR #822: preserve JSON escapes in length-constrained strings](https://github.com/mlc-ai/xgrammar/pull/822) | Open | Exact repair for the length-bound result. Its summary explicitly says it rejects unescaped U+0000 through U+001F in the `minLength` and `maxLength` path and fixes #800. |
| [PR #828: allow JSON escapes and count code points in length-bounded strings](https://github.com/mlc-ai/xgrammar/pull/828) | Open | Exact repair plus additional length accounting. It explicitly states that the bounded character class admitted the C0 range, adds that exclusion, identifies its first commit as equivalent to #822, and fixes #800. |

This is enough to classify the bounded-value part as a duplicate even though
issue #800 was originally framed around completeness. The issue exposes the
same faulty production, and both proposed fixes name the soundness consequence
measured by finding 007.

## Historical equivalent and recurrence

| Source | Status on 2026-08-25 | Relationship |
| --- | --- | --- |
| [Issue #286: Grammars compiled from JSON schemas accept invalid JSON input](https://github.com/mlc-ai/xgrammar/issues/286) | Closed as completed | Earlier report of the same JSON lexical violation in the generic JSON Schema string path. It showed a raw C0 character accepted inside an otherwise unconstrained string on XGrammar 0.1.17. |
| [PR #318: Fix the incorrect acceptance of some invalid characters in JSON strings](https://github.com/mlc-ai/xgrammar/pull/318) | Merged | Fix for #286. Its description states that U+0000 through U+001F were incorrectly accepted and changes the generic JSON string production. |

Finding 007 is best understood as a constrained-path recurrence or divergence
after the generic path was fixed. Its unbounded control remains rejecting,
while the separate lowering selected by string constraints retains the faulty
character class.

## Partial overlaps that are not duplicates

| Source | Status on 2026-08-25 | Why it is different |
| --- | --- | --- |
| [Issue #636: raw control bytes when a schema key contains control characters](https://github.com/mlc-ai/xgrammar/issues/636) | Closed as completed | The trigger is a fixed property name containing a control character in the schema itself. Finding 007 uses an ordinary schema and generates a constrained value or dynamic property name. |
| [PR #655: escape JSON schema property keys](https://github.com/mlc-ai/xgrammar/pull/655) | Merged | Fixes #636 by serializing fixed schema keys correctly. It does not address constrained free-form strings. |
| [Issue #487: incomplete propertyNames and patternProperties support](https://github.com/mlc-ai/xgrammar/issues/487) | Closed as completed | Covers keyword composition and trailing content. A maintainer comment mentions intersecting `propertyNames` with the standard JSON string regex, but neither the report nor its reproducer covers raw C0 acceptance. |
| [PR #594: support patternProperties alongside properties](https://github.com/mlc-ai/xgrammar/pull/594) | Merged | Fixes #487's composition cases, not the C0 behavior characterized in finding 007. |
| [Issue #749: pattern/format combined with length bounds silently drops the bounds](https://github.com/mlc-ai/xgrammar/issues/749) | Open | Another string-constraint compiler bug, but the lost constraint is length and the witness is an out-of-bound ordinary string. It does not concern JSON lexical validity. |
| [PR #683: enforce minLength/maxLength with pattern](https://github.com/mlc-ai/xgrammar/pull/683) | Open | Proposed partial composition of pattern and length constraints. It does not report or test C0 admission. |
| [PR #798: reject combining pattern/format with length constraints](https://github.com/mlc-ai/xgrammar/pull/798) | Open | Alternative handling for #749. It rejects an unsupported keyword combination and does not address a length-only or pattern-only C0 witness. |
| [PR #796: reject pattern/format combined with length constraints](https://github.com/mlc-ai/xgrammar/pull/796) | Closed without merge | Earlier proposal for #749's distinct dropped-bound problem. |
| [PR #853: optimize JSON Schema string length constraints](https://github.com/mlc-ai/xgrammar/pull/853) | Open | Architectural overlap. It proposes reusing the complete JSON string grammar and adding decoded-length metadata, which would remove the divergent bounded production. Its stated trackers are performance issues #805 and #852 rather than finding 007 or #800. |

## Search formulations

Repository-wide issue and pull request searches used combinations of:

- `control character`, `control byte`, `unescaped control`, and `raw byte`
- `invalid JSON`, `JSON string`, `RFC 8259`, and `standard string regex`
- `U+0000`, `U+001F`, and `C0`
- `minLength`, `maxLength`, `pattern`, and `propertyNames`
- `compile_json_schema`, escapes, and JSON parsing

The most useful matches were #286, #318, #636, #655, #800, #822, and #828.
Queries combining `propertyNames` with control, escape, invalid JSON, U+0000,
or U+001F found no equivalent report. Queries combining `pattern` with control
characters found no separate soundness report beyond the constrained-string
scope already described by #800 and its repair PRs.

## Upstream disposition

No issue or pull request was drafted, opened, or modified during this search.
