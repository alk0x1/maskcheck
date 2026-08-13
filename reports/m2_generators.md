# M2 report: generators and shrinking

M2 adds Hypothesis strategies for supported JSON Schemas, compact valid instances, and
dependent schema-instance pairs. It also adds a predicate-driven shrinker that reduces
a failing pair while preserving the relationship between the schema and its instance.

## Public seams

| API | Contract |
|---|---|
| `schemas(max_depth=3)` | Legal Draft 2020-12 schemas inside the reference oracle's supported subset |
| `instances(schema)` | Compact JSON text valid against that schema |
| `schema_instance_pairs(max_depth=3)` | A schema and dependent valid instance that shrink together |
| `find_minimal(predicate)` | Smallest generated pair Hypothesis finds that preserves the caller's failure predicate |

Generated schemas cover strings with length bounds, bounded and unbounded numbers and
integers, booleans, nulls, enums, consts, closed objects with required and optional
properties, bounded arrays, and `anyOf`. Nesting is explicitly capped.

The distribution is deliberately biased toward constrained-decoding boundaries:

- keys that share prefixes (`a`, `ab`, `abc`);
- short adjacent object members and permuted property order;
- literal and `\uXXXX` spellings of Unicode strings and keys;
- integer spellings including `-0`, zero fractional parts, and exponent forms;
- bounded numerics and partially shared enum values;
- nested arrays and objects with dense closing delimiters.

Structural whitespace is never generated. This preserves the compact tokenization a
model normally produces rather than testing a pretty-printer's tokenization.

## Exit criteria

The deterministic exit sweep generated **10,000 schema-instance pairs**. For every
pair it checked:

1. the schema with `Draft202012Validator.check_schema`;
2. the instance with `jsonschema`;
3. every character prefix with the witness-certified reference oracle;
4. final completeness with the reference validator.

Result on this machine:

```text
10000 passing, 0 failing
1 passed in 23.38s
```

A separate smoke sweep sent 500 generated pairs through the complete XGrammar/GPT-2
path: schema compilation, tokenization round-trip, allowed masks, matcher advancement,
completion, and stop-token handling. It completed without exceptions. Its violation
records are not classified here because engine finding discovery and deduplication are
M3 work.

## Shrinking proof

The injected failure predicate models an engine that rejects escaped spellings of a
schema-fixed string. Hypothesis reduced it to:

```python
schema = {"const":"é"}
instance = '"\\u00e9"'
```

That is two lines, below the milestone's ten-line requirement. The minimized schema is
legal, the instance validates against it, and the failure predicate still holds.

## Harness bug found

The 10,000-pair sweep exposed an oracle bug at a prefix inside an escaped supplementary
Unicode character. JSON spells 🙂 as the surrogate pair `\ud83d\ude42`, but the string
parser counted the two escapes as two characters and padded a `minLength` witness one
character short. The parser now consumes or completes the low surrogate as part of the
same Unicode character. A direct regression test and the original 10,000-pair sweep
both pass.

## Limits

Random generation intentionally stays inside the reference oracle's supported subset.
It does not generate `pattern`, `allOf`, `not`, conditional schemas, `multipleOf`, or
other keywords on which the oracle must abstain. Recursive `$ref` remains covered by
the handwritten corpus rather than the random strategy, where unbounded recursive
instances would undermine predictable size and shrinking. The string-level oracle's
byte-fragment coverage gap also remains; that is independent of M2 generation.
