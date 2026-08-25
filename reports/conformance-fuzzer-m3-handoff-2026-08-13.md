# Conformance fuzzer M3 handoff

Date: 2026-08-13

## Goal and authoritative context

Continue M3 of the constrained-decoding conformance fuzzer in the current repository. Read `AGENTS.md` first. It defines the project, properties, milestones, and verification rules. Do not infer project behavior from this handoff when the repository can answer directly.

The verified checkpoint is commit `40c20b8` (`Build M2 generators and M3 conformance matrix`). It contains M2, all three M3 engine adapters, four tokenizer registrations, all three property drivers, the Outlines classification correction, the shared llguidance/XGrammar bounded-exponent regression, research, and documentation.

Relevant existing artifacts:

- `AGENTS.md`: project specification and working rules
- `README.md`: current findings and milestone status
- `reports/m2_generators.md`: M2 exit evidence
- `reports/m3_research.md`: primary-source version/API audit, including XGrammar 0.2.5 and post-rewrite `main`, Outlines numeric-keyword source behavior, and tokenizer revisions
- `findings/001_*.py` through `findings/006_*.py`: standalone XGrammar reproducers

## Verified checkpoint state

The project environment now pins:

- XGrammar `0.2.4`, the newest release with a CPython 3.12 wheel
- llguidance `1.8.0`
- outlines-core `0.2.14`

Full suite at the checkpoint:

```text
243 passed in 38.70s
```

All six existing XGrammar findings also reproduced in a separate Python 3.10 environment with latest stable `xgrammar==0.2.5`. The research agent additionally reproduced them on post-compiler-rewrite `main`; exact commit and primary sources are in `reports/m3_research.md`.

## Classification decisions already made

1. Outlines silently ignoring standard numeric value constraints is a soundness disagreement, not a capability gap. `outlines-core==0.2.14` compiles schemas containing `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, and `multipleOf`, produces the same regex as the unbounded type, and accepts values rejected by Draft 2020-12. The former harness-side keyword filter was removed before commit `40c20b8`.
2. llguidance rejecting exponent spellings when numeric bounds are present is the same conceptual root cause as XGrammar finding 006, not a separate class. Minimal case:

```python
schema = {"type": "number", "minimum": 10}
text = "1e1"
```

Both engines accept `1e1` for unbounded `number` and reject it when the bound is added, although its numeric value is 10.

3. Mistral's standalone canonical first token is context-sensitive. All three engines reject it in the same way. Completeness records at token index 0 for Mistral are warnings about the tokenizer/context contract, not independent engine bugs.

## Uncommitted harness robustness change

The working tree has five modified files:

- `fuzzer/tokenizers.py`
- `fuzzer/properties/completeness.py`
- `fuzzer/sweep.py`
- `tests/test_tokenizations.py`
- `tests/test_sweep.py`

Reason: the first 25-pair pilot was interrupted after about 13 minutes. `Tokenizer.tokenizations()` limited the number of returned alternatives but not the number of paths explored, so non-roundtripping decompositions could explode.

The uncommitted fix:

- adds an explicit `max_search_states` budget, default 4096
- caches bounded enumeration results
- reports budget exhaustion as a completeness `inconclusive`
- adds `on_cell_complete` to `run_sweep()` for observable/persistable cell progress

Test-first evidence:

```text
Before implementation: 2 failed
  AttributeError: Tokenizer has no enumerate_tokenizations
  TypeError: run_sweep() got unexpected keyword argument on_cell_complete

After implementation:
8 passed in 2.42s
```

`git diff --check` is clean. The full suite has not been rerun after these five uncommitted changes. Do that before committing them.

## Completed 25-pair M3 pilot

Deterministic configuration:

```text
pairs=25, max_depth=3, seed=20260813
alternate tokenizations=4
tokenization search states=512
soundness walks/schema=20, max tokens=32
viability depth=4, candidates=16, branch limit=64
```

Each cell below is `decidable / inconclusive / violations`.


| Engine     | Tokenizer | Completeness | Soundness     | Viability     |
| ---------- | --------- | ------------: | -------------: | -------------: |
| xgrammar   | gpt2      | 79 / 0 / 7   | 434 / 66 / 0  | 724 / 38 / 0  |
| xgrammar   | qwen2.5   | 74 / 0 / 7   | 391 / 109 / 1 | 800 / 14 / 0  |
| xgrammar   | mistral   | 111 / 3 / 25 | 416 / 84 / 2  | 185 / 77 / 0  |
| xgrammar   | llama3    | 88 / 0 / 7   | 388 / 112 / 0 | 704 / 30 / 0  |
| llguidance | gpt2      | 79 / 0 / 5   | 431 / 69 / 0  | 1009 / 35 / 0 |
| llguidance | qwen2.5   | 74 / 0 / 5   | 395 / 105 / 0 | 1118 / 9 / 0  |
| llguidance | mistral   | 111 / 3 / 25 | 416 / 84 / 0  | 177 / 79 / 0  |
| llguidance | llama3    | 88 / 0 / 5   | 392 / 108 / 0 | 945 / 28 / 0  |
| outlines   | gpt2      | 79 / 0 / 6   | 433 / 67 / 20 | 626 / 26 / 0  |
| outlines   | qwen2.5   | 74 / 0 / 6   | 425 / 75 / 12 | 592 / 6 / 0   |
| outlines   | mistral   | 111 / 3 / 25 | 427 / 73 / 11 | 183 / 79 / 0  |
| outlines   | llama3    | 88 / 0 / 6   | 427 / 73 / 20 | 603 / 10 / 0  |


Interpretation so far:

- Zero viability violations.
- Zero llguidance soundness violations.
- Outlines produced 63 soundness records total. Visible samples all match the single silent numeric-bounds omission root cause. Deduplicate, do not report 63 bugs.
- XGrammar produced three soundness records. They minimized to a new root cause described below.
- Non-Mistral completeness records visibly revisit bounded exponents, Unicode escape policy, and schema property order. They still need systematic root-cause classification before a report claims a count.
- The pilot output is not yet saved under `reports/`. The exact deterministic configuration above can reproduce it, but saving a classified report should be preferred over pasting raw samples.

## New high-value XGrammar soundness root cause

The random walks found XGrammar completing raw C0 control characters inside JSON strings. Minimal current case:

```python
schema = {"type": "string", "minLength": 1, "maxLength": 3}
text = "\"\x1b\""
```

Draft 2020-12 validation rejects the text because raw U+001B is illegal inside a JSON string. With GPT-2, Qwen 2.5, and Llama 3 tokenizers, the text tokenizes as IDs `[1, 215, 1]`; XGrammar accepts all three and reports completion. llguidance and Outlines reject token 215.

The minimal custom vocabulary `['"', '\x1b', '"']` also reproduces:

```text
xgrammar 0.2.4 accept_token steps: [True, True, True], completed=True
xgrammar 0.2.5 accept_token steps: [True, True, True], completed=True
```

Important correction to an earlier hypothesis: this is not limited to the token-level automaton. The final check against `xgrammar 0.2.4` returned:

```text
accept_string=True completed=True
accept_token_steps=[True, True, True] completed=True
```

For the unbounded schema `{"type":"string"}`, both 0.2.4 and 0.2.5 reject all raw U+0000 through U+001F characters. Adding string length constraints opens at least raw BEL, DC2, and ESC, observed in the pilot. The exact triggering keyword combination and affected C0 range are not yet mapped.

This appears to be a new, character-level soundness root cause caused by the bounded-string compiler. It is likely higher severity than the six completeness findings because the engine can emit invalid JSON.

Do not claim it against post-rewrite `main` yet. Only stable 0.2.4 and 0.2.5 are verified for this new case.

## Recommended next steps

1. Use TDD to characterize the new XGrammar bug across `minLength` only, `maxLength` only, both, boundary values, all U+0000 through U+001F, 0.2.4, 0.2.5, and current `main`. Verify whether the behavior is schema compilation or matcher-specific.
2. Add a focused regression test and a standalone `findings/007_*.py` reproducer only after the root cause is stable and minimized.
3. Save a classified 25-pair pilot report under `reports/`, separating occurrences from distinct root causes and separating Mistral context warnings from findings.
4. Run the full test suite. If green, commit the five harness robustness changes and any completed finding/report work. No AI attribution or em dashes.
5. Add durable per-cell report persistence, not just a callback, before the long sweep. Consider parallel execution by independent engine/tokenizer cell only after preserving determinism and thread/process safety.
6. Run a larger pilot, then the full M3 sweep. Treat it as coverage/occurrence measurement, not proof of absence. The byte-level oracle gap remains a later source of potentially new token-boundary classes.



- **Testar em chave, não só em valor.** Se `minLength` numa chave via `propertyNames` ou `patternProperties` abre a mesma porta, a severidade sobe bastante.
- **Testar outras keywords de string.** Se `pattern` ou `format` também abrem, a causa não é bounds de comprimento, é o caminho de compilação de string restrita inteiro, e a issue muda de tamanho.

## Suggested skills

- `diagnosing-bugs`: characterize and minimize the bounded-string/C0 soundness failure before documenting it.
- `tdd`: add the regression and persistence behavior test-first.
- `research`: verify the new case on official XGrammar `main` and gather primary-source compiler context if needed.
- `mode-research-poc`: useful if the next session focuses on explaining the shared numeric-value versus spelling model or the new bounded-string compiler failure as a broader class.

## Working rules to retain

Read real state first. Reproduce end to end before changing code. Do not trust raw counts as distinct bugs. Run verifiers before claiming completion. Do not file issues or publish anything without explicit user direction.
