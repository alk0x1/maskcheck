# maskcheck

Check that a constrained decoding engine can actually produce every document your JSON
Schema allows.

Engines like XGrammar, llguidance and Outlines are what make "reply with JSON matching
this schema" work in vLLM and SGLang. Before every token, the engine greys out the
options that would break your schema, and the model picks from what is left.

That list can be wrong in two directions. If it leaves in something illegal you get
broken JSON, your parser throws, and you notice. If it greys out something legal, a
correct answer becomes impossible for the model to write, nothing errors anywhere, and
you never find out. `maskcheck` tests for both against your own schemas.

```bash
maskcheck verify --engine xgrammar --tokenizer meta-llama/Llama-3.1-8B --schemas ./schemas
```

It writes valid documents for each of your schemas, walks the engine through them one
token at a time, and fails the run if the engine refused a token it should have allowed.
It drives the engine APIs directly, with no GPU, no model and no inference, so a run
takes seconds.

## Install

No clone needed. Each engine is a separate extra, so testing one does not install the
other two:

```bash
pip install 'conformance-fuzzer[xgrammar] @ git+ssh://git@github.com/alk0x1/conformance_fuzzer'
```

Swap `[xgrammar]` for `[llguidance]`, `[outlines]`, or `[engines]` for all three. The
repository is private today, so the `ssh` form above is the one that works, using your
own key. Once it is public, this works too:

```bash
pip install 'conformance-fuzzer[xgrammar] @ git+https://github.com/alk0x1/conformance_fuzzer'
```

Naming an engine you did not install reports what is missing and how to get it, and
exits 2. It does not fail with an import error.

## Check your schemas

`--schemas` takes a file, a directory searched for `*.json`, or a glob. `--tokenizer`
takes any Hugging Face tokenizer id, or one of the four short ids pinned by this repo
(`gpt2`, `qwen2.5`, `mistral`, `llama3`).

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

Output from that run, verbatim:

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

Those are two real bugs in XGrammar 0.2.4, not harness noise. The first block says the
engine refuses `quantity` as the opening key, because property order is significant by
default, so a document listing the keys in any other order than the schema declares them
cannot be produced at all. The second says it refuses `e` after `480`, rejecting exponent
notation for a value JSON Schema counts as an integer. Both are silent in production.

### Reading a block

Each block is self-contained so it can be pasted into an issue without this repository.
It names the property, the engine version, the tokenizer, the step, the prefix accepted
so far, the token involved, and the witness document. Characters below U+0020 are always
written as `<U+00XX>` rather than emitted raw, so a block survives a terminal and a copy
paste. Repeated violations are grouped one block per distinct cause, so a schema failing
the same way forty times is reported once with a count.

## Use it in CI

`maskcheck verify` exits non-zero on a violation, so it needs no wrapper script.

```yaml
name: Schema check

on: [push, pull_request]

jobs:
  maskcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install 'conformance-fuzzer[xgrammar] @ git+https://github.com/alk0x1/conformance_fuzzer'
      - run: maskcheck verify --engine xgrammar --tokenizer gpt2 --schemas ./schemas
```

The repository is private today, so that install line needs credentials in CI: a
deploy key, or a token with read access. It works as written once the repository is
public.

| Exit code | Meaning |
|---|---|
| 0 | No violation in any property named by `--fail-on` |
| 1 | A violation was found in a fatal property |
| 2 | The run could not start: unknown or uninstalled engine, unreadable schema, tokenizer that will not load |

This is worth gating because engine upgrades and model swaps silently change which
tokens are legal. The bugs recorded in [RESEARCH.md](RESEARCH.md) were first seen on
xgrammar 0.2.3 and still reproduce on 0.2.5, so "it worked last release" is not
evidence.

Start with `--fail-on completeness` if you want the silent failures to break the build
while you triage the rest, or `--fail-on none` to report without ever failing.

## Options

| Flag | Default | What it does |
|---|---|---|
| `--engine` | required | `xgrammar`, `llguidance` or `outlines` |
| `--tokenizer` | required | Hugging Face id, or `gpt2` / `qwen2.5` / `mistral` / `llama3` |
| `--schemas` | required | A file, a directory searched for `*.json`, or a glob |
| `--revision` | repo default | Pin the tokenizer to a Hugging Face revision |
| `--instances` | 10 | Valid documents generated per schema, for completeness |
| `--walks` | 25 | Random walks per schema, for soundness |
| `--max-steps` | 64 | Token budget for one soundness walk |
| `--seed` | 0 | Seed for generation and walks, so a run repeats exactly |
| `--fail-on` | both | Which properties are fatal, or `none` |

## What it checks, and what it cannot

Two properties. **Completeness** asks whether every valid document can still be
produced, which is the silent failure. **Soundness** asks whether everything the engine
produces is valid, which is the loud one.

Read a clean run as "found nothing in what it could reach", not as "proved correct":

- Completeness only tests documents the built-in generator can produce. A schema using
  `pattern` or another keyword it does not model is skipped and named in the output,
  not checked.
- Soundness is a random walk. On a complex schema most walks hit the token budget
  without finishing a document, and those are counted as inconclusive rather than as
  checks. Raise `--max-steps` to convert them into real checks.
- A walk whose tokens split a multi-byte character cannot be judged as text, and is
  also counted as inconclusive rather than reported as a violation.

## Development

```bash
git clone git@github.com:alk0x1/conformance_fuzzer
cd conformance_fuzzer
uv sync --extra engines     # the test suite drives all three engines
uv run pytest
```

`maskcheck` is the tool built on top of a research harness that hunts correctness bugs
in these engines. The findings it has produced, the reference oracle it checks against,
and the project's scope and milestones are in [RESEARCH.md](RESEARCH.md).

## License

Apache 2.0. See [LICENSE](LICENSE). For reference, the engines under test are Apache
2.0 (XGrammar, outlines-core) and MIT (llguidance).
