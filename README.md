# maskcheck

Check whether a constrained-decoding engine can produce the JSON documents your schema
allows, and save a concrete witness when it cannot.

Engines such as XGrammar, llguidance, and Outlines power structured model output. Before
each token, they mask out choices that would break a JSON Schema. If that mask admits an
illegal document, downstream parsing breaks loudly. If it rejects a legal one, a valid
answer becomes unreachable and nothing reports the problem. `maskcheck` checks both.

**8 distinct conformance findings · 3 engines · 5 released versions, plus XGrammar
main.** The evidence and standalone reproducers are in [RESEARCH.md](RESEARCH.md).

```bash
maskcheck verify --engine xgrammar --tokenizer meta-llama/Llama-3.1-8B --schemas ./schemas
```

It generates valid documents for each schema, feeds them through the engine token by
token, and fails when the engine refuses a legal token. It calls the engine APIs
directly, with no GPU, model, or inference.

## Install

No clone or credentials needed. Each engine is a separate extra, so testing one does
not install the other two:

```bash
pip install 'maskcheck[xgrammar] @ git+https://github.com/alk0x1/maskcheck'
```

Swap `[xgrammar]` for `[llguidance]`, `[outlines]`, or `[engines]` for all three.
Naming an engine you did not install reports what is missing and how to install it, then
exits 2 instead of raising an import error.

## Check your schemas

`--schemas` accepts a JSON Schema file, a directory searched for `*.json`, or a glob.
`--tokenizer` accepts a Hugging Face tokenizer id, or one of the pinned short ids:
`gpt2`, `qwen2.5`, `mistral`, and `llama3`.

```bash
mkdir -p schemas-demo
cat > schemas-demo/feature.json <<'JSON'
{
  "type": "object",
  "properties": {
    "enabled": {"type": "boolean"}
  },
  "required": ["enabled"],
  "additionalProperties": false
}
JSON

maskcheck verify --engine xgrammar --tokenizer gpt2 --schemas schemas-demo
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
  completeness      2 checks, 0 skipped, 0 violations
  soundness         25 checks, 0 skipped, 0 violations

No violations found.
```

The example completes every soundness walk within the default token budget. Open-ended
strings and larger schemas can still exhaust that budget; those walks are reported as
inconclusive, never counted as passing checks.

### Reading a violation

When a violation is found, its block is a standalone witness suitable for an issue. It
names the property, engine version, tokenizer, accepted prefix, blocked token, and
witness document. Control characters are escaped, and repeated instances of the same
cause are grouped together.

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
      - run: pip install 'maskcheck[xgrammar] @ git+https://github.com/alk0x1/maskcheck'
      - run: maskcheck verify --engine xgrammar --tokenizer gpt2 --schemas ./schemas
```

| Exit code | Meaning |
|---|---|
| 0 | No violation in any property named by `--fail-on` |
| 1 | A violation was found in a fatal property |
| 2 | The run could not start: unknown or uninstalled engine, unreadable schema, or tokenizer that will not load |

Engine upgrades and model swaps silently change which tokens are legal. Start with
`--fail-on completeness` to gate the silent failures while you triage the rest, or use
`--fail-on none` to report without ever failing the job.

## Options

| Flag | Default | What it does |
|---|---|---|
| `--engine` | required | `xgrammar`, `llguidance`, or `outlines` |
| `--tokenizer` | required | Hugging Face id, or `gpt2` / `qwen2.5` / `mistral` / `llama3` |
| `--schemas` | required | A file, a directory searched for `*.json`, or a glob |
| `--revision` | repo default | Pin the tokenizer to a Hugging Face revision |
| `--instances` | 10 | Valid documents generated per schema for completeness |
| `--walks` | 25 | Random walks per schema for soundness |
| `--max-steps` | 64 | Token budget for one soundness walk |
| `--seed` | 0 | Seed for generation and walks, so a run repeats exactly |
| `--fail-on` | both | Which properties are fatal, or `none` |

## What it checks, and what it cannot

**Completeness** asks whether valid documents can still be produced, the silent failure.
**Soundness** asks whether the engine can produce an invalid document, the loud failure.

Read a clean run as "found nothing in what it could reach," not as "proved correct":

- Completeness only checks documents the built-in generator can produce. Unsupported
  schema keywords are skipped and named in the output.
- Soundness is a random walk. A walk that reaches `--max-steps` without finishing is
  inconclusive. Raise the limit to give it more room.
- A walk whose tokens split a multi-byte character cannot be judged as text, so it is
  also inconclusive rather than reported as a violation.

## Development

```bash
git clone https://github.com/alk0x1/maskcheck
cd maskcheck
uv sync --extra engines
uv run pytest
```

`maskcheck` is the tool built on a research harness. Its findings, reference oracle,
scope, and milestones are in [RESEARCH.md](RESEARCH.md).

## License

Apache 2.0. See [LICENSE](LICENSE). The engines under test are Apache 2.0 (XGrammar,
outlines-core) and MIT (llguidance).
