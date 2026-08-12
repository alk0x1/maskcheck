# Conformance fuzzer for constrained-decoding engines

Differential testing harness that hunts **correctness** bugs in constrained-decoding
engines (XGrammar, llguidance, Outlines). Not performance bugs.

The bet: these engines are heavily optimized for speed and validated by testing, not by
proof. The translation from a character-level grammar to a token-level automaton is
where the bugs should live, and nobody is systematically hunting them across tokenizers.

## The three properties

| Property | Statement | Failure symptom |
|---|---|---|
| Soundness | Every accepted token sequence decodes to a string valid against the schema | Loud: downstream parse error |
| Completeness | Every valid string has at least one accepted tokenization | **Silent**: valid outputs become unreachable, output distribution skews, nobody notices |
| Viability | Every allowed token has at least one legal completion | Generation walks into a dead end |

Completeness is the interesting one, and every finding so far is a completeness finding.

## Findings

Against **xgrammar 0.2.3**. Each file in `findings/` runs standalone with only
`xgrammar` and `jsonschema` installed.

| # | Finding | Severity | Confidence |
|---|---|---|---|
| [001](findings/001_xgrammar_integer_negative_zero.py) | `-0` is unreachable for `{"type":"integer"}` | Low | Unambiguous |
| [002](findings/002_xgrammar_integer_zero_fractional_part.py) | `1.0`, `1e2`, `0.0` unreachable for `{"type":"integer"}` | Low | Spec-dependent |
| [003](findings/003_xgrammar_carriage_return_whitespace.py) | Carriage return not accepted as JSON whitespace | **Medium** | Unambiguous |
| [004](findings/004_xgrammar_property_order_default.py) | Only one property ordering reachable by default | Medium | Documented knob |

All four are character-level, so they are tokenizer-independent.

**003 is the one that matters most.** RFC 8259 defines exactly four whitespace
characters: space, tab, LF, CR. XGrammar accepts three and rejects CR at every
position, so any output with CRLF line endings is unreachable and generation is blocked
mid-document with no valid continuation. Unlike `-0`, this is text models really emit.

**004 is the archetype the project is looking for.** Nothing errors, output stays valid,
but `n! - 1` of the `n!` valid key orderings cannot be generated and the output
distribution is skewed toward the schema author's declaration order. It is a documented
default (`any_order=False`) rather than a bug, and a caller who never reads that doc has
no way to notice.

Not yet filed upstream (M4).

## Running it

```bash
uv sync
uv run pytest                       # the harness's own tests
uv run python findings/003_*.py     # any single reproducer, standalone
```

## Layout

```
fuzzer/
  engines/        one adapter per engine behind a uniform interface
    base.py       EngineAdapter / Matcher protocols, CapabilityGap
    xgrammar.py
  oracle/
    validator.py  reference JSON Schema validation (character level)
    reference.py  reference token-level acceptor, deliberately slow, witness-certified
  properties/
    completeness.py   valid instance -> every token must be allowed
    differential.py   engine mask vs reference mask, at every step, both directions
  corpus.py       handwritten suite of token-boundary-stressing schemas
  tokenizers.py   tokenizer registry and encode/decode conventions
  findings.py     Violation record
findings/         standalone reproducers, one per distinct root cause
```

## Design decisions worth knowing

**The oracle certifies its positive answers.** `Reference.viable_prefix` does not reason
that a completion exists, it constructs one and runs it through `jsonschema`. A false
"viable" is therefore impossible unless `jsonschema` is wrong. That concentrates the
entire correctness burden on the negative side, where the rule is: **abstain, never
guess.** Anything the parser cannot model (`pattern`, `allOf`, `not`, `if`/`then`,
`multipleOf`) raises `Unsupported`, and the driver counts it as undecidable rather than
folding it into agreement.

This caught two of my own mistakes while writing the tests. `{"n":1.5` looks dead for
`{"type":"integer"}` until the oracle produces `1.5e1`, which is 15.0 and has a zero
fractional part. `{"a":"x","a` looks like a duplicate key until the oracle produces
`{"a":"x","ab":"","abc":""}`.

**Bounded numeric search abstains rather than concludes.** For `{"n":30` under
`minimum: 10, maximum: 20`, appending digits grows a number and appending an exponent
can shrink it, so an exhausted bounded search is not a proof of non-viability. The
reference distinguishes "pruning killed every branch" (a definite answer) from "a branch
was cut off by the bound" (raises `Unsupported`). This costs coverage on bounded numeric
schemas and buys never reporting a phantom violation.

**Whitespace around the document is not reported.** RFC 8259 permits it, no engine
allows it, and reporting it would bury the real findings under thousands of identical
ones. `Reference(..., allow_surrounding_whitespace=True)` restores the literal reading.
Interior whitespace is still checked, which is how 003 surfaced.

**`is_completed()` is not `is_terminated()`.** A valid instance with no EOS token
emitted is *completed* but not *terminated*, and an engine can consider a document
complete while never allowing a stop token, so generation cannot end. The `Matcher`
protocol keeps both, plus `can_stop()`, and the completeness driver reports them as
distinct failures.

## Milestone status

- **M0 — spine.** Done. XGrammar + GPT-2 + one hardcoded schema, completeness driver
  end to end. GPT-2 spells `{"a":"x"}` as `{"` `a` `":"` `x` `"}`, so even the baseline
  case exercises boundary-spanning tokens.
- **M1 — reference oracle.** Done. Reference validator and acceptor, 23-case handwritten
  corpus, differential driver. Every remaining disagreement between the reference and
  XGrammar is understood and filed as 001-004.
- **M2 — generators.** Not started. Random schemas via Hypothesis, valid instance
  generation, shrinking.
- **M3 — the sweep.** Not started. All engines, all tokenizers, all three properties.
- **M4 — disclosure.** Not started.

## Scope

In: XGrammar and llguidance (Outlines if cheap), JSON Schema only, at least four
structurally different tokenizers, no GPU and no model.

Out: performance measurement, regex and full CFG constraints, formal proof, building a
competing engine. Bugs found in target engines are reported, not fixed here.

A clean report is a valid result and ends the project at M3.
