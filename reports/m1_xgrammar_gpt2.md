# M1 differential report: XGrammar vs reference, GPT-2

Full-vocabulary differential sweep of the handwritten corpus. At every step along the
canonical tokenization of every corpus instance, the engine's allowed mask is compared
against the reference acceptor's viable set, in both directions.

| | |
|---|---|
| Engine | xgrammar 0.2.3 |
| Tokenizer | gpt2 (50257 tokens) |
| Oracle | reference acceptor, witness-certified, `jsonschema` 4.26.0 draft 2020-12 |
| Corpus | 23 cases, 58 instances |
| Scan | full vocabulary at every step, not sampled |
| Wall clock | 329 s |

## Results

| Property | Violations |
|---|---|
| Soundness (engine allows what no valid document contains) | **0** |
| Completeness (engine forbids what the reference can complete) | 88 |

Counted as step-level records: one per (instance, step, direction) where the two masks
disagreed. 38 of 58 instances produced at least one; they collapse into 18 distinct
disagreement buckets and then into 6 root causes.

**XGrammar was sound on every case tested.** Every disagreement is a completeness
disagreement, which is consistent with the project's premise: soundness failures are
loud and get fixed, completeness failures are silent.

## Root causes

All six are character-level and therefore tokenizer-independent.

| # | Root cause | Records | Confidence |
|---|---|---|---|
| [003](../findings/003_xgrammar_carriage_return_whitespace.py) | CR not accepted as JSON whitespace | >=49 | Unambiguous |
| [004](../findings/004_xgrammar_property_order_default.py) | Only the schema's declaration order of properties is reachable | 24 | Documented default |
| [006](../findings/006_xgrammar_bounded_number_exponents.py) | Numeric bounds make exponent spellings unreachable | >=3 | Unambiguous |
| [005](../findings/005_xgrammar_escaped_fixed_strings.py) | `\uXXXX` spellings of keys, enums and consts unreachable | 2 | Unambiguous |
| [001](../findings/001_xgrammar_integer_negative_zero.py) | `-0` unreachable for `{"type":"integer"}` | 2 | Unambiguous |
| [002](../findings/002_xgrammar_integer_zero_fractional_part.py) | Draft-6+ integers with a zero fractional part unreachable | mixed only | Spec-dependent |

Counts are exact where a bucket has a single cause and given as a lower bound where one
bucket mixes causes: two buckets (8 records) contain both CR tokens and numeric-spelling
tokens at the same step, and 002 was never observed in a bucket of its own. The six
causes together account for all 18 buckets, with no unexplained residue.

Four of the six are unambiguous conformance gaps. 004 is a documented default rather
than a bug, and 002 depends on which JSON Schema draft the engine targets.

## Reading the two biggest classes

**003 dominates by step count** because CR is legal whitespace at every structural
position, so it disagrees at nearly every step of nearly every instance. That inflates
its step count relative to its severity, but the severity is real on its own terms:
CRLF-formatted output is unreachable and generation blocks mid-document.

**004 is the archetype this project exists to find.** Nothing errors, every output is
still valid, but `n! - 1` of the `n!` valid key orderings cannot be generated. A caller
who never reads the `any_order` documentation has no way to notice that the output
distribution is pinned to the schema author's declaration order.

## Coverage and limits

Honest accounting of what this sweep did *not* decide:

- **Undecidable tokens were counted, not hidden.** Byte-level BPE splits multi-byte
  characters across tokens, so neither piece is valid UTF-8 alone and a string-level
  oracle cannot judge them. Roughly 7% of the vocabulary per step falls in this
  category, along with special tokens. A byte-level reference would close this gap and
  is the single biggest coverage improvement available.
- **Steps landing mid-character were skipped entirely**, for the same reason.
- **Bounded numeric schemas abstained often during this recorded sweep.** At M1, an
  exhausted bounded completion search raised rather than guessed, which made
  `bounded_number` cost ~60 s per instance. The reference now decides these prefixes
  with exact decimal interval arithmetic; the counts and wall clock above remain the
  historical M1 result.
- **Whitespace around the document is out of scope by decision**, not by oversight. See
  the README.
- **One engine, one tokenizer.** Nothing here says anything about llguidance, Outlines,
  or about whether any of these findings interact with a different vocabulary. That is
  M3.

## Reproducing

```bash
uv run pytest                            # harness tests, including all six findings' regressions
uv run python findings/003_*.py          # any single finding, standalone
```
