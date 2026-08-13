# M3 integration research

Research date: 2026-08-13.

This note uses only first-party package metadata, repositories, source code, and Hugging Face model repositories. Package probes were installed under `/private/tmp`; no project dependency was changed.

## Recommendation

The smallest defensible M3 matrix is 12 rows:

| Engine | Version/path | Tokenizers |
| --- | --- | --- |
| XGrammar | `0.2.4` in the Python 3.12 project; audit `0.2.5` separately | all four below |
| llguidance | `1.8.0` | all four below |
| Outlines | `outlines_core==0.2.14`, the default JSON backend pinned by Outlines `1.3.3` | all four below |

Outlines is cheap enough to include. Its first-party core exposes the state machine directly, without a model or inference loop. Report schema compilation failures as capability gaps, separately from soundness, completeness, and viability violations. Outlines supports a narrower schema subset than llguidance and the reference validator.

Use these exact public tokenizer repositories:

1. `openai-community/gpt2`
2. `Qwen/Qwen2.5-0.5B-Instruct`
3. `mistralai/Mistral-7B-v0.1`
4. `Xenova/llama3-tokenizer`

Always call `encode(text, add_special_tokens=False)` and `decode(ids, skip_special_tokens=False)`. Record the repository revision, Transformers version, engine version, vocabulary length, and special-token policy in every matrix row.

There is one blocking classification issue before a long sweep: Mistral's initial metaspace token is context-sensitive. The live probes below show all three engines rejecting its standalone canonical first token for a minimal valid JSON string. Keep Mistral in the matrix, but classify this start-of-sequence tokenizer behavior explicitly before treating every occurrence as an independent engine violation.

## XGrammar current-version audit

### First-party release and compiler facts

The latest stable PyPI release is `xgrammar 0.2.5`, uploaded 2026-07-22. GitHub also marks `v0.2.5` as the latest release. See [PyPI's live package metadata](https://pypi.org/pypi/xgrammar/json) and the [official `v0.2.5` release](https://github.com/mlc-ai/xgrammar/releases/tag/v0.2.5). The published `0.2.5` artifacts are five CPython 3.10 wheels, with no source distribution or CPython 3.11/3.12 wheel. Because this project requires Python 3.12, the stable-version audit used a separate Python 3.10 environment rather than changing the project environment.

XGrammar-2 is released, not planned work. The project's 2026-05-04 announcement describes it as a backward-compatible major upgrade for agent applications. Its stated scope is Structural Tag, cross-grammar caching, repetition-state compression, batching and speculative-decoding APIs, and TVM-FFI-backed Python, C++, Rust, and JavaScript deployment. It is broader than, and should not be described as, a JSON Schema semantic rewrite. See the [official XGrammar-2 announcement](https://blog.mlc.ai/2026/05/04/xgrammar-2-fast-customizable-structured-generation).

A separate compiler-construction rewrite landed on `main` after `v0.2.5`, on 2026-07-28:

- [PR 745](https://github.com/mlc-ai/xgrammar/pull/745) replaces the JSON-Schema-to-EBNF-string round trip with direct grammar-tree construction. Its first-party description says that parsing, constraint folding, reference resolution, formatting, and accepted-language behavior are preserved.
- [PR 727](https://github.com/mlc-ai/xgrammar/pull/727) streams grammar expressions into one shared finite-state machine. Its description says that this reduces intermediate allocation and copying while preserving the resulting FSM structure.

These two changes are on `main`, not in the latest stable wheel. Their documented goal is compiler construction and performance, not repair of the six conformance findings below. Release `0.2.4` does contain other correctness fixes, including integer `multipleOf` soundness and overlapping `oneOf` rejection, but its notes name none of these six findings. See the [official `v0.2.4` release notes](https://github.com/mlc-ai/xgrammar/releases/tag/v0.2.4).

### Runtime evidence against stable and rewritten code

This is local runtime evidence, not an upstream claim. All six standalone files under `findings/` were run in two isolated environments:

1. the published `xgrammar==0.2.5` CPython 3.10 wheel;
2. a source build of official `main` at commit [`ba00e8bd4d85be96a2fe8cdc561cb08bed899db6`](https://github.com/mlc-ai/xgrammar/commit/ba00e8bd4d85be96a2fe8cdc561cb08bed899db6), which includes PRs 745 and 727.

| Finding originally observed on `0.2.3` | `0.2.5` wheel | post-rewrite `main` |
| --- | --- | --- |
| integer `-0` rejected | reproduced | reproduced |
| zero-fraction/exponent integer spellings rejected | reproduced | reproduced |
| carriage return JSON whitespace rejected | reproduced | reproduced |
| default object-property order restriction | reproduced | reproduced |
| escaped spellings of schema-fixed strings rejected | reproduced | reproduced |
| exponent spellings of bounded numbers rejected | reproduced | reproduced |

Every script exited zero and printed its `REPRODUCED` marker in both environments. The `0.2.3` findings are therefore not obsolete in either the latest stable release or the post-rewrite `main` revision tested on 2026-08-13. Keep the original version in each reproducer's provenance, but add `0.2.5` and the exact `main` commit to any disclosure writeup.

## llguidance

### Version and construction

The current stable Python package is `llguidance 1.8.0`, released 2026-08-11, with Python 3.10 or newer. See [PyPI release metadata](https://pypi.org/project/llguidance/) and the [tagged package definition](https://github.com/guidance-ai/llguidance/blob/v1.8.0/pyproject.toml).

Use the already-loaded fast Hugging Face tokenizer so every engine sees the same tokenizer object and vocabulary length:

```python
from llguidance import LLMatcher, LLTokenizer
from llguidance.hf import from_tokenizer

ll_tokenizer = from_tokenizer(
    hf_tokenizer,
    n_vocab=len(hf_tokenizer),
    slices=LLTokenizer.json_slices(),
)
grammar = LLMatcher.grammar_from_json_schema(schema)
message = LLMatcher.validate_grammar(grammar, ll_tokenizer)
if message:
    # Parse warnings separately; a validation error is CompilationFailed.
    ...
matcher = LLMatcher(ll_tokenizer, grammar, log_level=0)
if matcher.is_error():
    ...
```

The official helper serializes a fast tokenizer's Rust backend, including added tokens from `tokenizer_config.json`, and takes explicit vocabulary and EOS overrides. See [`llguidance/hf.py`](https://github.com/guidance-ai/llguidance/blob/v1.8.0/python/llguidance/hf.py). The tagged type definitions document all matcher methods used below: [`_lib.pyi`](https://github.com/guidance-ai/llguidance/blob/v1.8.0/python/llguidance/_lib.pyi).

### Uniform interface mapping

| Harness operation | llguidance operation | Important semantics |
| --- | --- | --- |
| allowed token IDs | `compute_logit_bias()` | Returns one byte per vocabulary entry; `200` means allowed and `0` means disallowed. This is simpler for the first adapter than unpacking `compute_bitmask()`. |
| accept | `consume_token(token_id)` | Returns false and leaves the matcher permanently in an error state on rejection. Check membership first when callers may probe invalid IDs. |
| completed | `is_accepting()` | Means the grammar is satisfied and generation may end. |
| engine stopped | `is_stopped()` | Means no more non-EOS tokens are accepted. It is also true on error, so pair it with `not is_error()`. |
| reset | `reset()` | Returns to the initial state. |
| stop IDs | `LLTokenizer.eos_tokens` | Supports one or more EOS IDs. |

The protocol's `is_terminated()` means EOS was consumed, which is not the same as llguidance's `is_stopped()`. In a successful live probe, completion made `is_accepting()` and `is_stopped()` true before EOS, with EOS as the only allowed token. Consuming EOS kept both flags true. The adapter should therefore track whether it consumed an EOS token locally:

```python
is_completed = matcher.is_accepting() and not matcher.is_error()
can_stop = bool(set(ll_tokenizer.eos_tokens) & allowed_mask)
is_terminated = eos_was_consumed
```

This preserves the distinctions already present in the harness instead of collapsing completed, stoppable, and terminated.

### JSON Schema dialect and documented support

llguidance aims either to produce a grammar conforming to JSON Schema Draft 2020-12 or to return an error, subject to documented departures. Its official support table includes types, `enum`, `const`, arrays, objects, local `$ref`, string constraints, numeric bounds, `multipleOf`, and combinators. `oneOf`, `allOf`, `patternProperties`, `minProperties`/`maxProperties`, patterns, and formats have documented partial coverage. Remote and external references are unsupported. See the [official JSON Schema support document](https://github.com/guidance-ai/llguidance/blob/v1.8.0/docs/json_schema.md).

Documented semantic departures that the M3 classifier must retain:

- Object properties follow schema order.
- `format` is enforced by default, unlike ordinary annotation-only validation unless a format checker is enabled.
- Keys generated through `additionalProperties` or `patternProperties` are not guaranteed unique.
- Printable `\uXXXX` alternatives are disabled by default unless `json_allow_general_unicode_escapes` is enabled.
- Whitespace is accepted inside the root JSON value but not before or after it by default.

Do not use `lenient=True` in conformance runs. It ignores unsupported keywords and coerces `oneOf` to `anyOf`, which could turn capability gaps into apparent soundness bugs.

## Outlines

### Version and the model-free path

The current stable package is `outlines 1.3.3`, released 2026-08-06. See [PyPI's versioned metadata](https://pypi.org/pypi/outlines/1.3.3/json). It pins `outlines_core==0.2.14`, and `outlines_core` is its default JSON Schema backend. See the [tagged dependency declaration](https://github.com/dottxt-ai/outlines/blob/1.3.3/pyproject.toml) and [backend selection](https://github.com/dottxt-ai/outlines/blob/1.3.3/src/outlines/backends/__init__.py).

The high-level Outlines backend builds a logits processor around a model wrapper, but the same first-party core is directly usable without a model:

```python
import json
from outlines_core import Guide, Index, Vocabulary
from outlines_core.json_schema import build_regex_from_schema

vocabulary = Vocabulary.from_pretrained(tokenizer_id, revision=revision)
regex = build_regex_from_schema(json.dumps(schema))
index = Index(regex, vocabulary)
guide = Guide(index)

allowed = set(guide.get_tokens())
if token_id in allowed:
    guide.advance(token_id, return_tokens=False)
completed = guide.is_finished()
guide.reset()
```

This is the library's documented Python composition. See the [tagged outlines-core README](https://github.com/dottxt-ai/outlines-core/blob/0.2.14/README.md). The Python bindings expose `get_tokens`, `advance`, `is_finished`, `reset`, packed-mask writing, and `Vocabulary.from_pretrained`; see the [tagged binding source](https://github.com/dottxt-ai/outlines-core/blob/0.2.14/src/python_bindings/mod.rs).

The adapter is therefore small:

| Harness operation | outlines-core operation | Important semantics |
| --- | --- | --- |
| allowed token IDs | `Guide.get_tokens()` | Already returns token IDs, so no tensor or model is required. |
| accept | membership check, then `Guide.advance()` | Invalid advancement raises `ValueError`; return false instead of poisoning the guide. |
| completed | `Guide.is_finished()` | The DFA is in a final state. |
| reset | `Guide.reset()` | Directly supported in `0.2.14`. |
| stop | vocabulary EOS ID | At a final state the allowed list is only EOS, but advancing EOS raises because the guide has no EOS transition. |

The last point is a real interface mismatch. Outlines' own tests assert that a finished guide offers EOS but cannot advance it, and the high-level logits processor avoids advancing final EOS. See [`tests/test_guide.py`](https://github.com/dottxt-ai/outlines-core/blob/0.2.14/tests/test_guide.py) and the [Outlines backend source](https://github.com/dottxt-ai/outlines/blob/1.3.3/src/outlines/backends/outlines_core.py). Record `is_completed()` and `can_stop()` normally. For `is_terminated()`, either record a capability gap or track that the adapter observed EOS without claiming the core consumed it. The report must say which choice was made.

### JSON Schema dialect and support

outlines-core does not claim conformance to a specific JSON Schema draft. Its source documents a keyword subset. It supports common types, `enum`, `const`, object and array constraints, `prefixItems`, string constraints, `allOf`, `anyOf`, `oneOf`, and local references. Recursive references are expanded only to a default maximum depth of 3. See the [official `0.2.14` schema module](https://github.com/dottxt-ai/outlines-core/blob/0.2.14/src/json_schema/mod.rs).

Important limits:

- Remote references are unsupported.
- Standard `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, and `multipleOf` are absent from the documented supported-constraint list. The list names only Outlines-specific digit-count numeric constraints for numbers and integers.
- Not every schema accepted by Draft 2020-12 validation is compilable to Outlines' regular-expression representation.
- The generated regular expression and DFA can grow substantially with schema and vocabulary complexity.

The exact `0.2.14` parser explains what happens. Its top-level dispatch selects a parser from structural keys such as `properties`, combinators, `enum`, `const`, `$ref`, and `type`. For `type: number`, the numeric parser inspects only `minDigitsInteger`, `maxDigitsInteger`, `minDigitsFraction`, `maxDigitsFraction`, `minDigitsExponent`, and `maxDigitsExponent`. For `type: integer`, it inspects only `minDigits` and `maxDigits`. It has no rejection branch for the five standard numeric value keywords. See the [tagged parser dispatch](https://github.com/dottxt-ai/outlines-core/blob/0.2.14/src/json_schema/parsing.rs#L49-L63) and [tagged numeric parsers](https://github.com/dottxt-ai/outlines-core/blob/0.2.14/src/json_schema/parsing.rs#L421-L502).

### Runtime evidence for numeric bounds

This is local runtime evidence from the published `outlines_core==0.2.14` wheel, kept separate from the source facts above. For both `{"type": "number"}` and `{"type": "integer"}`, each of the following schemas compiled successfully:

| Added keyword | Invalid candidate used | Generated regex versus unbounded type | Candidate accepted by regex |
| --- | ---: | --- | --- |
| `minimum: 10` | `9` | identical | yes |
| `maximum: 10` | `11` | identical | yes |
| `exclusiveMinimum: 10` | `10` | identical | yes |
| `exclusiveMaximum: 10` | `10` | identical | yes |
| `multipleOf: 2` | `3` | identical | yes |

Each candidate fails the corresponding Draft 2020-12 assertion, whose official validation vocabulary defines all five as numeric assertion keywords. See the [JSON Schema Draft 2020-12 numeric validation specification](https://json-schema.org/draft/2020-12/json-schema-validation#name-validation-keywords-for-numeric).

The observed behavior is therefore compilation with silent omission, not explicit rejection. Do not classify these cases as `CapabilityGap` or `CompilationFailed`. When applying the project's Draft 2020-12 oracle, record the resulting accepted-invalid instance as a soundness disagreement. Do not remove the keywords before compilation.

## Tokenizer matrix

All four repositories were loaded anonymously with `AutoTokenizer.from_pretrained`, so none requires a Hugging Face access token or license-acceptance gate as of the research date. The repository pages and files are the authoritative sources for access state and tokenizer configuration.

| Short ID | Exact repository and observed revision | Family and structure | Vocabulary and special-token behavior |
| --- | --- | --- | --- |
| `gpt2` | [`openai-community/gpt2`](https://huggingface.co/openai-community/gpt2), `607a30d783dfa663caf39e06633721c8d4cfcd7e` | Original GPT-2 byte-level BPE, ByteLevel pre-tokenizer and decoder, no normalizer. See the [tokenizer graph](https://huggingface.co/openai-community/gpt2/blob/main/tokenizer.json). | 50,257 total IDs. BOS, EOS, and UNK are all `<|endoftext|>` ID 50256; no PAD. Encoding JSON adds no BOS. The [model config](https://huggingface.co/openai-community/gpt2/blob/main/config.json) records vocabulary and BOS/EOS IDs. |
| `qwen2.5` | [`Qwen/Qwen2.5-0.5B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct), `7ae557604adf67be50417f59c2c2f167def9a775` | Large byte-level BPE with Unicode-aware regex splitting and NFC normalization. See the [tokenizer graph](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/main/tokenizer.json). | 151,643 base IDs and 151,665 tokenizer IDs. No BOS or UNK. EOS `<|im_end|>` ID 151645; PAD `<|endoftext|>` ID 151643. The [tokenizer config](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/main/tokenizer_config.json) sets `add_bos_token` false and lists the added tokens. |
| `mistral` | [`mistralai/Mistral-7B-v0.1`](https://huggingface.co/mistralai/Mistral-7B-v0.1), `27d67f1b5f57dc0953326b2601d68371d40ea8da` | SentencePiece/Llama-style BPE with Metaspace `▁` word boundaries and byte fallback. See the [tokenizer graph](https://huggingface.co/mistralai/Mistral-7B-v0.1/blob/main/tokenizer.json). | 32,000 IDs. UNK 0, BOS `<s>` 1, EOS `</s>` 2; no PAD. Default encoding prepends BOS because `add_bos_token` is true, so the harness must disable special tokens. See its [tokenizer config](https://huggingface.co/mistralai/Mistral-7B-v0.1/blob/main/tokenizer_config.json) and [model config](https://huggingface.co/mistralai/Mistral-7B-v0.1/blob/main/config.json). |
| `llama3` | [`Xenova/llama3-tokenizer`](https://huggingface.co/Xenova/llama3-tokenizer), `72bff9ee09897a16b3b4b2b9995fecb0bfa7dbe6` | Public tokenizer-only Llama 3 artifact, modern byte-level BPE with a different Unicode/digit split from Qwen. See the [tokenizer graph](https://huggingface.co/Xenova/llama3-tokenizer/blob/main/tokenizer.json). | 128,000 base IDs and 128,256 total IDs. BOS `<|begin_of_text|>` 128000, EOS `<|end_of_text|>` 128001; no PAD or UNK. Raw JSON encoding adds neither token. See the [tokenizer config](https://huggingface.co/Xenova/llama3-tokenizer/blob/main/tokenizer_config.json). |

These are not four arbitrary model sizes. They exercise four materially different vocabulary geometries: old 50K GPT-2 byte BPE, 151K Qwen byte BPE with NFC, 32K metaspace plus byte fallback, and 128K Llama 3 byte BPE with different pre-tokenization boundaries.

### Vocabulary-size rule

Use `len(hf_tokenizer)` as the mask universe, not the model config's padded `vocab_size`. Qwen reports 151,936 model logits but defines tokenizer IDs only through 151,664. The Llama 3 derivatives similarly may pad model embeddings beyond the tokenizer's actual IDs. Supplying `n_vocab=len(hf_tokenizer)` to llguidance and the explicit tokenizer vocabulary to other engines keeps the compared ID set identical.

### Mistral start-of-sequence caveat

For the valid JSON text `"a"`, Transformers produced Mistral IDs `[345, 28708, 28739]`, whose full decode is `"a"`. Token 345 is displayed as `▁"`; decoding or normalizing token pieces independently can instead treat it as a leading space plus quote.

In isolated probes against `{"const": "a"}`:

```text
llguidance 1.8.0: first token 345 disallowed; consume_token entered an error
outlines_core 0.2.14: first token 345 absent from Guide.get_tokens()
project XGrammar adapter: first token 345 absent from the mask
```

The llguidance error began:

```text
Parser Error: token " \"" doesn't satisfy the grammar; forced bytes: got '"'; applying ' '
```

This is not enough evidence to file three engine bugs. It demonstrates that the harness's architecture assumes a context-independent token-to-text contribution that is not true for the Mistral tokenizer at the beginning of a standalone decode. Before the long sweep, add an end-to-end tokenizer contract test and choose one explicit policy:

1. Treat full-sequence `tokenizer.decode(ids)` as authoritative, consistent with the current project definition. Then report this as a distinct cross-engine tokenizer-normalization disagreement, not thousands of separate completeness findings.
2. Define generation context and token byte contributions the same way each production sampler does. Then the tokenizer adapter must encode instances in that context, not with standalone `encode(instance)` alone.

The first policy is smaller and matches the existing harness, but the final report must state it.

## Live verification

The current stable packages were installed only under `/private/tmp`. A minimal `const` schema was compiled and its canonical tokenization consumed step by step.

Observed llguidance output for the tokenizers without the Mistral caveat:

```text
llguidance 1.8.0
openai-community/gpt2 validate '' before_eos (True, True, 'NoExtension', [50256], [50256]) after_reset (False, False, 'NotStopped')
Qwen/Qwen2.5-0.5B-Instruct validate '' before_eos (True, True, 'NoExtension', [151645], [151645]) after_reset (False, False, 'NotStopped')
Xenova/llama3-tokenizer [57793, 1] [True, True] True True ''
```

Observed outlines-core output:

```text
openai-community/gpt2 accepted [True, True, True] finished True
Qwen/Qwen2.5-0.5B-Instruct accepted [True, True] finished True
mistralai/Mistral-7B-v0.1 accepted [False] finished False
Xenova/llama3-tokenizer accepted [True, True] finished True
```

These probes verify the API paths and the tokenizer access assumptions. They are not a conformance sweep.
