# M3 checkpoint

Date: 2026-08-24

## Verified state

The repository is at commit `5f2e419` after the constrained-string
characterization and M3 robustness work. The full local suite completed with:

```text
277 passed in 40.31s
```

Pinned engine versions are XGrammar 0.2.4, llguidance 1.8.0, and
outlines-core 0.2.14. The tokenizer matrix contains GPT-2, Qwen 2.5,
Mistral, and Llama 3 registrations at pinned revisions.

Milestone state:

| Milestone | State | Evidence |
|---|---|---|
| M0 | Complete | XGrammar and GPT-2 completeness path runs end to end |
| M1 | Complete | Handwritten corpus and reference comparison classified into findings 001-006 |
| M2 | Complete | 10,000 generated pairs completed without a harness failure and shrinking met its exit criterion |
| M3 | In progress | Three engines, four tokenizers, three properties, and a classified 25-pair pilot are complete; the long run has not started |
| M4 | Not started | No upstream submission has been made |

The 25-pair pilot used seed 20260813, schema depth 3, four alternate
tokenizations, a 512-state tokenization budget, 20 soundness walks per schema,
32 maximum generated tokens, and viability depth 4. The detailed configuration
is in [m3_25_pair_pilot.md](m3_25_pair_pilot.md).

## Findings and classifications

### Standalone XGrammar findings

| ID | Property | Distinct cause | Verification state |
|---|---|---|---|
| 001 | Completeness | Negative zero is excluded from integer syntax | Reproduced on 0.2.3, 0.2.5, and post-rewrite main |
| 002 | Completeness | Integer grammar excludes valid zero-fraction spellings | Reproduced on 0.2.3, 0.2.5, and post-rewrite main; interpretation depends on targeted JSON Schema draft |
| 003 | Completeness | Carriage return is omitted from JSON structural whitespace | Reproduced on 0.2.3, 0.2.5, and post-rewrite main |
| 004 | Completeness | Default object compilation follows declaration order | Reproduced on 0.2.3, 0.2.5, and post-rewrite main; documented configuration tradeoff |
| 005 | Completeness | Schema-fixed strings exclude equivalent escaped spellings | Reproduced on 0.2.3, 0.2.5, and post-rewrite main |
| 006 | Completeness | Numeric bounds constrain decimal spelling rather than represented value | Reproduced on 0.2.3, 0.2.5, and post-rewrite main |
| 007 | Soundness | Constrained string compilation loses JSON lexical exclusions | The complete grid is verified on both XGrammar 0.2.4 and 0.2.5; open issue #800 covers the length-bound case and open PRs #822 and #828 propose fixes; current main is unverified |

Findings 001-006 are documented in the earlier M1 and research reports. Finding
007 is standalone, uses a three-entry custom vocabulary, and downloads no
tokenizer.

### Finding 007 characterization

The characterization ran the entire matrix once in one Python process. Each real
tokenizer and its XGrammar compiler were created once and reused across every
schema and code point. A separate three-entry vocabulary covered the same cases
without an external tokenizer.

All 32 characters from U+0000 through U+001F were tested. The input text was
constructed with `chr()` only inside Python. Saved source, tables, and reports
contain labels such as `U+001B`, never the tested bytes themselves.

For one-character string values:

| Constraint | Accepted by `accept_string` | Interpretation |
|---|---:|---|
| No constraint | 0 of 32 | Baseline preserves JSON lexical exclusion |
| `minLength: 0` | 0 of 32 | Neutral minimum stays on the baseline path |
| `minLength: 1` | 30 of 32 | Length-constrained path admits invalid JSON text |
| `minLength: 2` | 0 of 32 | The one-character sample is below the schema minimum |
| `maxLength: 0` | 0 of 32 | The one-character sample is above the schema maximum |
| `maxLength: 1` | 30 of 32 | Length-constrained path admits invalid JSON text |
| `maxLength: 2` | 30 of 32 | Length-constrained path admits invalid JSON text |
| Both bounds with a range containing 1 | 30 of 32 | Same constrained-length behavior |
| Both bounds excluding length 1 | 0 of 32 | The one-character sample is outside the permitted range |
| Empty pattern | 0 of 32 | Simplifies to baseline behavior |
| Pattern matching exactly one character | 32 of 32 | The pattern path is affected and includes the two exclusions retained by the length path |
| Email format | 0 of 32 | The one-character sample does not satisfy the format shape, so this result does not settle format handling in general |

The two code points that remain excluded by the affected length-bound columns are
U+000A and U+000D. The one-character pattern excludes none of the 32 tested code
points. The saved 0.2.5 aggregate is in
[finding_007_xgrammar_0.2.5_grid.md](finding_007_xgrammar_0.2.5_grid.md).
The upstream duplicate search and direct links are recorded in
[finding_007_upstream_search_2026-08-25.md](finding_007_upstream_search_2026-08-25.md).

Bounded property names repeat the length-constraint result. This raises impact
because the behavior is not limited to string values.

GPT-2, Qwen 2.5, and Llama 3 produced the same `accept_string` and token-step
results as the custom vocabulary. Mistral produced the same character-level
result, while its token-step path was rejected at the known initial-context
boundary. That Mistral result remains a tokenizer-context warning rather than a
separate engine cause.

The pattern result rules out the narrow hypothesis that only length bounds are
affected. The current evidence points to more than one constrained-string
compilation path failing to retain JSON's lexical character exclusions.

### Other M3 engine classifications

The pilot identified five conceptual causes after deduplication:

1. XGrammar and llguidance constrain bounded numeric spellings rather than values.
2. Equivalent escaped spellings of schema-fixed strings are excluded.
3. Object member reachability follows schema declaration order.
4. Outlines compiles standard numeric value constraints without enforcing them.
5. XGrammar constrained strings can complete with text rejected by the strict JSON parser.

No viability cause was found in the bounded pilot. This is coverage evidence, not
proof of absence. The retained pilot aggregate does not map every completeness
witness back to an engine, so the classified report deliberately avoids invented
per-engine attribution.

## Harness state

The latest robustness change prevents alternate-tokenization enumeration from
expanding without an explicit limit:

- enumeration has a configurable state budget, defaulting to 4096;
- bounded results are cached;
- budget exhaustion is reported as inconclusive rather than as agreement;
- sweep cells can invoke an `on_cell_complete` callback;
- tests cover the budget and callback behavior.

These changes fixed the immediate pilot interruption. The callback is observability
only. Durable per-cell persistence and resume support do not yet exist.

## Current limitations

1. Finding 007 has not been checked against current XGrammar main.
2. The length-2 columns used a one-character sample to test range boundaries. A
   second grid with valid length-2 samples is needed to characterize those branches
   independently of ordinary length rejection.
3. The email-format sample establishes rejection only for a one-character input.
   Format-shaped inputs containing a labeled test character are needed before making
   a general claim about the format compiler path.
4. The pilot's retained aggregate lacks durable witness-to-engine mapping.
5. No long M3 run has been performed.
6. No issue has been filed and no upstream pull request has been opened by this project.

## Remaining work

Finding 007 upstream status:

1. Open issue #800 covers the length-bound portion of finding 007.
2. Open PRs #822 and #828 explicitly address the same excluded-character requirement.
3. Issue #800 substantially overlaps the pattern path, although its pattern example
   focuses on lost valid escapes rather than the full 32-character acceptance grid.
4. No equivalent propertyNames-specific report was found.
5. No new issue draft is warranted while the open duplicate and fixes are active.

Before the long M3 run:

1. Add durable per-cell persistence with atomic writes and resume support.
2. Preserve minimized witnesses with engine, tokenizer, property, seed, schema,
   instance, and version metadata.
3. Add root-cause classification keys so reports count conceptual causes separately
   from occurrences.
4. Run a larger pilot to validate persistence and deterministic replay.
5. Run the full matrix only after those exit checks pass.

## Value proposals

These are proposed deliverables, not completed or published work.

### Upstream issues

| Proposal | Audience | Value | Readiness |
|---|---|---|---|
| XGrammar issue #800 supporting evidence | XGrammar maintainers and users | Adds stable-version, custom-vocabulary, pattern, and property-name evidence to the existing report | Duplicate identified; no new issue should be filed while #800 is open |
| Outlines numeric-constraint omission report | Outlines maintainers and users | Makes silent omission of standard numeric constraints visible as a correctness issue | Behavior is classified; standalone upstream-oriented reproducer still needed |
| llguidance bounded-exponent report | llguidance maintainers and users | Shows that valid numeric values become unreachable because spelling is constrained | Shared cause is classified; engine-specific standalone evidence should be packaged |
| XGrammar findings 001-006 review | XGrammar maintainers | Converts the existing reproducible corpus into deduplicated, searchable upstream reports | Version evidence exists; duplicate research and maintainer-oriented issue drafts remain |

### Pull requests

| Proposal | Target | Value | Condition |
|---|---|---|---|
| Test-only conformance additions | Upstream engine repositories | Gives maintainers small regression cases without prescribing an internal fix | Submit only after issue discussion and repository-contribution review |
| Durable sweep checkpoints | This repository | Makes long runs resumable and preserves evidence after interruption | Highest-value harness change before the long run |
| Version matrix runner | This repository | Runs standalone findings against pinned releases and selected commits with one aggregate report | Build after the 0.2.5 verification workflow is proven manually |
| Classified report output | This repository | Separates occurrence volume from distinct causes and tokenizer warnings | Requires stable classification keys and persisted witnesses |

Target-engine implementation fixes remain outside this repository's scope. Upstream
test contributions may be valuable after maintainers confirm the expected behavior.

### Authorial tools

| Tool concept | Primary user | Value proposition | Smallest useful version |
|---|---|---|---|
| Constrained-string conformance matrix | Engine maintainers | Compares character-level and token-step behavior across schema keywords without model inference | Generalize the current single-process script behind the adapter interface |
| Cross-version finding verifier | Maintainers and issue authors | Answers whether a case affects stable releases, latest release, and selected commits without manual environment setup | Run each standalone finding in isolated pinned environments and emit one status table |
| Reproducer packager | Fuzzer operators | Turns a minimized witness into a dependency-light standalone file with version and expected-result metadata | Template from findings 001-007 plus automatic validation |
| Root-cause ledger | Fuzzer operators | Prevents large occurrence counts from being mistaken for many independent defects | Persist fingerprints, classifications, evidence links, and warning categories |
| Tokenizer-context auditor | Engine integrators | Separates engine behavior from start-context and decoding-contract mismatches | Check isolated and contextual round trips for the registered tokenizer matrix |
| Resumable conformance runner | Researchers and maintainers | Makes long deterministic matrices operationally reliable on CPU-only machines | Atomic cell files, manifest, resume command, and final aggregation |

The strongest near-term value is not a larger random run. It is a verified 0.2.5
package for finding 007, duplicate research, and a maintainer-ready issue if the case
is not already known. The strongest medium-term product is a resumable,
version-aware conformance runner that emits deduplicated evidence rather than raw
record totals.

## Recommended sequence

1. Recheck issue #800 and PRs #822 and #828 before any finding 007 upstream action.
2. Close the valid length-2 and format-shaped characterization gaps.
3. Decide whether the propertyNames evidence adds value to issue #800.
4. Add durable per-cell persistence and replay metadata.
5. Run a larger pilot.
6. Run the long M3 matrix.
7. Prepare remaining deduplicated upstream reports only after the matrix is stable.

No upstream action should be taken without a final review of the standalone evidence,
version claims, and duplicate status.
