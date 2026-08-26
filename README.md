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

Originally found against **xgrammar 0.2.3**. All six standalone reproducers still
reproduce on the latest stable `0.2.5` wheel and on post-compiler-rewrite `main` at
`ba00e8bd4d85be96a2fe8cdc561cb08bed899db6`.

| # | Finding | Severity | Confidence |
|---|---|---|---|
| [001](findings/001_xgrammar_integer_negative_zero.py) | `-0` is unreachable for `{"type":"integer"}` | Low | Unambiguous |
| [002](findings/002_xgrammar_integer_zero_fractional_part.py) | `1.0`, `1e2`, `0.0` unreachable for `{"type":"integer"}` | Low | Spec-dependent |
| [003](findings/003_xgrammar_carriage_return_whitespace.py) | Carriage return not accepted as JSON whitespace | **Medium** | Unambiguous |
| [004](findings/004_xgrammar_property_order_default.py) | Only one property ordering reachable by default | Medium | Documented knob |
| [005](findings/005_xgrammar_escaped_fixed_strings.py) | `\uXXXX` spellings of keys, enums and consts unreachable | Medium | Unambiguous |
| [006](findings/006_xgrammar_bounded_number_exponents.py) | Numeric bounds make exponent spellings unreachable | Low | Unambiguous |
| [007](findings/007_xgrammar_constrained_string_characters.py) | Constrained strings can complete with invalid JSON text | High | Unambiguous |

M3 has now reproduced 006 independently in **llguidance 1.8.0**: `1e1` is reachable
for an unbounded number and rejected as soon as `minimum: 10` is added. This is one
shared modeling failure, not two engine-specific root causes. Both compilers constrain
the decimal spelling instead of the numeric value represented by that spelling.

M3 also found a soundness disagreement in **outlines-core 0.2.14**. Schemas containing
standard numeric value constraints such as `minimum` or `maximum` compile successfully,
but the generated regex is identical to the unbounded type and accepts out-of-range
values. This is silent constraint omission, not a compilation or capability gap.

M3 finding 007 is character-level and tokenizer-independent. Length-bounded strings
and a one-character pattern can complete with text rejected by the strict JSON parser.
The same length-bound behavior occurs in property names. Both `accept_string` and
three-token matching reproduce it with a custom vocabulary. The complete grid is
verified on XGrammar 0.2.4 and 0.2.5. The length-bound case is already covered by
[XGrammar issue #800](https://github.com/mlc-ai/xgrammar/issues/800), with open fixes
in [PR #822](https://github.com/mlc-ai/xgrammar/pull/822) and
[PR #828](https://github.com/mlc-ai/xgrammar/pull/828).

All six are character-level, so they are tokenizer-independent. Full sweep numbers are
in [reports/m1_xgrammar_gpt2.md](reports/m1_xgrammar_gpt2.md): 58 instances, full
vocabulary scanned at every step, **zero soundness violations**, 88 completeness
records collapsing to these six causes.

**003 is the one that matters most.** RFC 8259 defines exactly four whitespace
characters: space, tab, LF, CR. XGrammar accepts three and rejects CR at every
position, so any output with CRLF line endings is unreachable and generation is blocked
mid-document with no valid continuation. Unlike `-0`, this is text models really emit.

**004 is the archetype the project is looking for.** Nothing errors, output stays valid,
but `n! - 1` of the `n!` valid key orderings cannot be generated and the output
distribution is skewed toward the schema author's declaration order. It is a documented
default (`any_order=False`) rather than a bug, and a caller who never reads that doc has
no way to notice.

**005 is more realistic than it first looks.** `"\u0061"` and `"a"` are the
same JSON string, and Python's `json.dumps` escapes non-ASCII *by default*
(`ensure_ascii=True`), so a large share of public JSON spells `é` as
`\u00e9`. A model that learned that convention will be blocked mid-string on any
schema with a non-ASCII key or enum value.

Not yet filed upstream (M4).

## Checking your own schemas

Install the harness and one engine, from a clone of this repository. The engines are
optional extras, so testing one does not install the other two:

```bash
pip install '.[xgrammar]'      # or [llguidance], [outlines], or [engines] for all three
```

Naming an engine that is not installed reports what is missing and how to get it. It
does not fail with an import error.

Point it at your schemas. `--schemas` takes a file, a directory searched for `*.json`,
or a glob. `--tokenizer` takes any Hugging Face tokenizer id, or one of the four short
ids pinned by this repo (`gpt2`, `qwen2.5`, `mistral`, `llama3`).

```bash
mkdir -p schemas-demo
cat > schemas-demo/order.json <<'JSON'
{
  "type": "object",
  "properties": {
    "sku": {"type": "string"},
    "quantity": {"type": "integer", "minimum": 1}
  },
  "required": ["sku", "quantity"],
  "additionalProperties": false
}
JSON

maskcheck verify --engine xgrammar --tokenizer gpt2 --schemas schemas-demo \
  --instances 6 --walks 20 --max-steps 200
```

Completeness generates valid documents for each schema and requires the engine to
allow every token of them. Soundness random-walks the engine's own allowed tokens and
requires every completed document to validate. The run exits non-zero when a violation
is found, so it drops into CI unchanged. Use `--fail-on` to choose which properties are
fatal (`--fail-on completeness`, or `--fail-on none` to report without failing).

Output from the run above, verbatim:

```text
maskcheck verify
  engine            xgrammar 0.2.4
  tokenizer         gpt2
  schemas           1 from schemas-demo
  fatal properties  completeness, soundness

  schemas checked   1
  schemas skipped   0
  completeness      6 checks, 0 skipped, 5 violations
  soundness         4 checks, 0 skipped, 0 violations, 16 inconclusive

  Inconclusive results ran but could not be judged: the walk hit the
  token budget before completing a document, or its tokens split a
  multi-byte character so the output is not text. Raise --max-steps to
  convert the first kind into real checks.

5 violations from 2 distinct causes.

==============================================================================
Cause 1 of 2: completeness violation
==============================================================================
  property              completeness
  reason                valid instance rejected: token not in allowed mask
  engine                xgrammar 0.2.4
  tokenizer             gpt2
  schema source         schemas-demo/order.json
  occurrences           4, all from this schema
  step index            1
  prefix so far         "{\""
  blocked token         id=40972 text="quant"
  witness document      "{\"quantity\":178.0,\"sku\":\"\\\\\\t\"}"
  schema                {"type": "object", "properties": {"sku": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1}}, "required": ["sku", "quantity"], "additionalProperties": false}

==============================================================================
Cause 2 of 2: completeness violation
==============================================================================
  property              completeness
  reason                valid instance rejected: token not in allowed mask
  engine                xgrammar 0.2.4
  tokenizer             gpt2
  schema source         schemas-demo/order.json
  step index            24
  prefix so far         "{\"sku\":\"é日\\t日a\\t\\\"🙂\\\\\\\"\",\"quantity\":480"
  blocked token         id=68 text="e"
  witness document      "{\"sku\":\"é日\\t日a\\t\\\"🙂\\\\\\\"\",\"quantity\":480e0}"
  schema                {"type": "object", "properties": {"sku": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1}}, "required": ["sku", "quantity"], "additionalProperties": false}
```

That is two real bugs in XGrammar 0.2.4, not harness noise. The first block says the
engine refuses `quantity` as the opening key: property order is significant by default,
so a document that lists the keys in a different order than the schema declares them
cannot be produced at all. The second says it refuses `e` after `480`, rejecting
exponent notation for a value JSON Schema counts as an integer. Both are silent in
production: the model never emits those documents and nothing reports an error.

Every block is self-contained on purpose. It names the property, the engine version,
the tokenizer, the step, the prefix accepted so far, the token involved, and the
witness document, so it can be pasted into an issue without this repository. Characters
below U+0020 are always written as `<U+00XX>` rather than emitted raw.

Repeated violations are grouped, one block per distinct cause, so a schema that fails
the same way forty times is reported once with a count.

## Running the harness itself

The test suite drives all three engines, so it needs all three installed.

```bash
uv sync --extra engines
uv run pytest                       # the harness's own tests
uv run pytest tests/test_m2_generators.py  # 10k generated-pair exit verifier
uv run python findings/003_*.py     # any single reproducer, standalone
```

## Layout

```
fuzzer/
  engines/        one adapter per engine behind a uniform interface
    base.py       EngineAdapter / Matcher protocols, CapabilityGap
    registry.py   engine lookup by name, optional imports, missing reported
    xgrammar.py
  generators/
    schemas.py    bounded Hypothesis strategy for supported JSON Schemas
    instances.py compact valid instances and dependent schema-instance pairs
  oracle/
    validator.py  reference JSON Schema validation (character level)
    reference.py  reference token-level acceptor, deliberately slow, witness-certified
  properties/
    completeness.py   valid instance -> every token must be allowed
    differential.py   engine mask vs reference mask, at every step, both directions
  corpus.py       handwritten suite of token-boundary-stressing schemas
  shrink.py       predicate-driven failure discovery and shrinking
  tokenizers.py   tokenizer registry and encode/decode conventions
  findings.py     Violation record
  report.py       one violation rendered as a self-contained block
  cli.py          maskcheck, the command over your own schemas
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

**Bounded numeric prefixes are solved arithmetically.** A partial mantissa defines an
exact decimal interval repeated at powers of ten, while a partial exponent defines a
set of integer scales. The reference intersects those sets with `minimum` and `maximum`
instead of exploring character suffixes. Positive answers still carry a witness that
passes `jsonschema`; impossible prefixes such as `30` under `[10, 20]` are rejected
without an arbitrary search cutoff.

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

- **M0, spine.** Done. XGrammar + GPT-2 + one hardcoded schema, completeness driver
  end to end. GPT-2 spells `{"a":"x"}` as `{"` `a` `":"` `x` `"}`, so even the baseline
  case exercises boundary-spanning tokens.
- **M1, reference oracle.** Done. Reference validator and acceptor, 23-case handwritten
  corpus, differential driver. Every disagreement between the reference and XGrammar is
  understood and filed as 001-006, with no unexplained residue.
- **M2, generators.** Done. Hypothesis schema and compact-instance strategies,
  dependent pair generation, and predicate-driven shrinking. The exit sweep checked
  10,000 pairs through schema validation, instance validation, every character prefix
  of the reference oracle, and final completeness without a crash. An injected escaped
  fixed-string bug shrinks to a two-line case. Full details are in
  [reports/m2_generators.md](reports/m2_generators.md).
- **M3, the sweep.** In progress. All three engines and all four tokenizers are wired;
  the three property drivers pass their end-to-end contract tests. The long matrix run
  remains. The current verified state, classified pilot, limitations, and proposed
  deliverables are in
  [reports/m3_checkpoint_2026-08-24.md](reports/m3_checkpoint_2026-08-24.md).
- **M4, disclosure.** Not started.

Alongside the milestones, the harness is now installable and runs over schemas a caller
supplies rather than only over generated ones. See
[Checking your own schemas](#checking-your-own-schemas).

## Scope

In: XGrammar and llguidance (Outlines if cheap), JSON Schema only, at least four
structurally different tokenizers, no GPU and no model.

Out: performance measurement, regex and full CFG constraints, formal proof, building a
competing engine. Bugs found in target engines are reported, not fixed here.

A clean report is a valid result and ends the project at M3.
