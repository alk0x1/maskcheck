# Conformance fuzzer for constrained-decoding engines

## 0. What this is

A differential testing harness that looks for **correctness** bugs in constrained-decoding engines (XGrammar, llguidance, Outlines), not performance bugs.

The bet: these engines are heavily optimized for speed and validated by testing, not by proof. The translation from a character-level grammar to a token-level automaton is where the bugs should live, and nobody is systematically hunting them across tokenizers.

Deliverable of the first pass is **reproducers filed as GitHub issues**, not a paper and not a proof. If the fuzzer finds nothing after M3, the project stops and that is a valid outcome.

---

## 1. Background an implementer needs

### The setup

A constrained-decoding engine takes a JSON Schema (or regex, or CFG) and produces, at each decoding step, a bitmask over the model's vocabulary marking which tokens are legal next.

Two levels are in play:

- **Character level.** The schema defines a language over strings.
- **Token level.** The model emits tokens. A tokenizer maps token sequences to strings.

The engine builds a token-level automaton. It is correct only if, for every token sequence it accepts, the decoded string is in the schema's language, and for every string in the language, some token sequence spelling it is accepted.

### The three properties under test


| Property         | Statement                                                                  | Failure symptom                                                                         |
| ---------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Soundness**    | Every accepted token sequence decodes to a string valid against the schema | Downstream parse error, broken JSON                                                     |
| **Completeness** | Every valid string has at least one accepted tokenization                  | Silent. Valid outputs become unreachable, output distribution is skewed, nobody notices |
| **Viability**    | Every allowed token has at least one legal completion                      | Generation walks into a dead end and either hangs or emits truncated output             |


Completeness is the interesting one. Soundness failures are loud, so they get fixed. Completeness failures are silent by construction.

### Why tokenizers matter

Token boundaries do not respect grammar boundaries. A single token can span the end of one schema element and the start of the next (`":` , `{"`, `,"`). An engine that walks the character automaton naively will reject such a token even though the resulting string is valid. This is the known "boundary mismatch" class, and it is tokenizer-dependent, so the same engine can be correct on one tokenizer and wrong on another.

---

## 2. Scope

### In scope (v1)

- Engines: **XGrammar** and **llguidance**. Add Outlines if the adapter is cheap.
- Constraint kind: **JSON Schema** only.
- Tokenizers: at least four with structurally different vocabularies (Llama 3, Qwen2.5, Mistral, GPT-2/tiktoken-style).
- No GPU, no model, no inference. The engines are driven directly through their APIs with synthetic token sequences.

### Out of scope (v1)

- Performance measurement of any kind
- Regex and full CFG constraints
- Any formal proof or Lean/Rocq mechanization
- Building a competing engine

### Non-goals to actively resist

- Do not "fix" bugs found in the target engines inside this repo. Report them.
- Do not add a web UI, a dashboard, or a plugin system.

---

## 3. Architecture

```
fuzzer/
  engines/          adapter per engine, one uniform interface
    base.py         EngineAdapter protocol
    xgrammar.py
    llguidance.py
    outlines.py
  oracle/
    validator.py    reference JSON Schema validation (character level)
    reference.py    reference token-level acceptor, deliberately slow and obviously correct
  generators/
    schemas.py      random JSON Schema generator (Hypothesis strategies)
    instances.py    valid instance generator for a given schema
    mutators.py     near-miss mutations of a valid instance
  properties/
    soundness.py
    completeness.py
    viability.py
  shrink.py         minimize (schema, string, tokenizer) triple
  report.py         emit a self-contained reproducer
  cli.py

```

### The uniform engine interface

Every adapter must expose exactly this. If an engine cannot support one of these, that is recorded as a capability gap, not worked around.

```python
class EngineAdapter(Protocol):
    def compile(self, schema: dict, tokenizer_id: str) -> Matcher: ...

class Matcher(Protocol):
    def allowed_mask(self) -> set[int]:   # token ids legal right now
        ...
    def accept(self, token_id: int) -> bool:  # advance state, False if rejected
        ...
    def is_terminated(self) -> bool: ...
    def reset(self) -> None: ...

```

### The reference acceptor

Deliberately naive, written for obvious correctness rather than speed: hold the decoded string so far, and for a candidate token, accept it iff `prefix + decode(token)` is a viable prefix of some string in the schema's language. Viability is decided by bounded search. This is the oracle. When an engine disagrees with it, the reference is assumed right until proven otherwise.

---

## 4. The three test drivers

### Completeness driver (highest value, build first)

```
for each (schema, tokenizer):
    s = generate_valid_instance(schema)
    toks = tokenizer.encode(s)
    m = engine.compile(schema, tokenizer)
    for i, t in enumerate(toks):
        if t not in m.allowed_mask():
            REPORT completeness violation at step i
        m.accept(t)
    if not m.is_terminated():
        REPORT non-termination on a valid complete instance

```

This is the sharpest instrument in the project. It directly targets boundary mismatch, it needs no search, and every hit is a real bug with a two-line reproducer.

Run it with **multiple tokenizations** of the same string, not just the canonical one, since completeness only requires that *some* tokenization is accepted, but the canonical one is the one the model actually produces.

### Soundness driver

Random-walk the allowed mask to a terminal state, decode, validate against the schema with the reference validator. Any accepted-but-invalid string is a soundness violation.

### Viability driver

At each step, sample k allowed tokens and check with bounded lookahead that a completion exists. Dead-end tokens are viability violations. Bound the lookahead depth and record it in the report, since this property is only approximately decidable here.

---

## 5. Generators

The schema generator is where fuzzing quality is won or lost. Bias it toward the constructs that stress token boundaries rather than toward broad JSON Schema coverage:

- Adjacent string fields with short keys, so `":` and `,"` land mid-token
- `enum` with values that share long prefixes
- `pattern` with anchors, escapes, and unicode classes
- Deep nesting and recursive `$ref`
- `anyOf` / `oneOf` where branches share prefixes
- `additionalProperties: false` with many optional keys
- Numeric formats: leading zeros, exponents, `-0`
- Unicode: multi-byte characters, characters that tokenize differently in different positions, surrogate pairs

Use Hypothesis so shrinking comes for free on the schema side.

---

## 6. Reproducer format

Every finding must emit a standalone file that runs without the fuzzer installed:

```python
# xgrammar completeness violation, Qwen2.5 tokenizer
# valid instance rejected at token index 4

SCHEMA = {...}          # minimized
INSTANCE = '{"a":"x"}'  # minimized, validates against SCHEMA
TOKENIZER = "Qwen/Qwen2.5-7B"

# expected: all tokens accepted
# actual:   token 4 (id=1234, ':"') not in allowed mask

```

If it does not run standalone, it is not a reproducer and maintainers will not act on it.

---

## 7. Milestones

Each milestone has a hard exit criterion. Do not start the next one before the current one is met.

**M0 — spine** One engine (XGrammar), one tokenizer, one hardcoded schema, the completeness driver running end to end. *Done when:* the canonical tokenization of a hand-written valid instance is accepted step by step.

**M1 — reference oracle** Reference validator and reference acceptor, with a small handwritten suite of known-tricky schemas. *Done when:* the reference and XGrammar agree on the whole handwritten suite, or the disagreement is understood.

**M2 — generators** Random schemas plus valid instance generation, biased as in section 5. Shrinking works. *Done when:* 10k random (schema, instance) pairs run without harness crashes, and any injected synthetic bug is minimized to under 10 lines.

**M3 — the sweep** All engines, all tokenizers, all three properties. Long run. *Done when:* a report exists stating, per engine and per tokenizer, how many cases ran and how many violations of each property were found. **A clean report is a valid result and ends the project here.**

**M4 — reproducers and disclosure** Minimize every distinct finding, dedupe by root cause, file issues upstream with standalone reproducers. *Done when:* issues are filed and linked from the repo README.

**M5 — writeup** Only if M3 found something. What the class of bug is, why token boundaries cause it, what the fix direction looks like.

---

## 8. Language choice

Python for the harness. Reason: XGrammar, llguidance and Outlines all expose Python bindings, Hypothesis is the best shrinking library available, and the harness is not performance-bound.

llguidance has a Rust crate, so a Rust adapter is possible later, but do not start there. Nothing about this project is fast enough to be worth the friction.

---

## 9. Open decisions to resolve before M3

1. **Multiple tokenizations.** Completeness formally requires that *some* tokenization is accepted. The model produces the canonical one. Decide whether a rejected canonical tokenization with an accepted alternative counts as a bug. Current position: yes, it counts, because the model cannot choose the alternative.
2. **Viability lookahead depth.** Deeper finds more, costs exponentially. Pick a bound and report it rather than pretending the property is decided.
3. **Oracle disagreement policy.** When the reference and every engine disagree with each other three ways, decide what is reported and how. Do not silently trust the reference.
