# Finding 007 PR validation

Date: 2026-08-25

## Thesis

Each proposed fix either rejects all 32 labeled inputs across length-bounded
string values, one-character pattern values, and length-bounded property names,
or the grid identifies the remaining schema path. A PR is incomplete for this
finding if any tested path still accepts any labeled input.

## Exact heads

| Pull request | Head SHA | State |
|---|---|---|
| [#822](https://github.com/mlc-ai/xgrammar/pull/822) | `91d85b5f40e47214401751ecdec5d97ea978e6a5` | Open, non-draft, unmerged |
| [#828](https://github.com/mlc-ai/xgrammar/pull/828) | `e14ff8d92c8daef6931fc42a11ecb971e5dce3c4` | Open, non-draft, unmerged |

Each head was cloned recursively, checked out detached at the recorded SHA,
built from source, and installed into a separate Python 3.10 environment. The
tokenizer dependencies matched the stable 0.2.5 grid: Transformers 4.57.6 and
Torch 2.13.0.

The exact source and build research is recorded in
[finding_007_pr_heads_research_2026-08-25.md](finding_007_pr_heads_research_2026-08-25.md).

## Method

The same single-process grid used for stable 0.2.5 ran once against each PR
head. Each run:

- tested U+0000 through U+001F;
- exercised `accept_string` and token-step acceptance;
- covered string `minLength`, `maxLength`, both bounds, and a one-character
  pattern;
- covered `propertyNames` with `minLength`, `maxLength`, and both bounds;
- used a three-entry custom vocabulary;
- repeated the matrix with GPT-2, Qwen 2.5, Mistral, and Llama 3, loading each
  tokenizer once per process;
- printed labels only and contained no tested bytes in source or output.

Saved aggregates:

- [PR #822 grid](finding_007_xgrammar_pr822_grid_2026-08-25.md)
- [PR #828 grid](finding_007_xgrammar_pr828_grid_2026-08-25.md)

## Negative control

The saved stable XGrammar 0.2.5 aggregate was reduced with the same parser. The
table counts invalid one-character inputs accepted out of 32 through both
matcher interfaces with the custom vocabulary.

| Build | Value `minLength: 1` | Value `maxLength: 1` | Value both bounds | Value pattern | `propertyNames` minimum | `propertyNames` maximum | `propertyNames` both |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stable 0.2.5 | 30 | 30 | 30 | 32 | 30 | 30 | 30 |

Under the stable length paths, U+000A and U+000D were the only two labels not
accepted. The one-character pattern accepted all 32. This control demonstrates
that the reducer distinguishes the unfixed behavior.

## Results

Counts below use the same definition: invalid inputs accepted out of 32. Zero
is the expected result.

| Build | Value `minLength: 1` | Value `maxLength: 1` | Value both bounds | Value pattern | `propertyNames` minimum | `propertyNames` maximum | `propertyNames` both |
|---|---:|---:|---:|---:|---:|---:|---:|
| PR #822 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| PR #828 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Both interfaces returned rejection for every selected cell. The same zero-count
result held for the custom vocabulary and all four real tokenizer contexts.

Verdict: both exact PR heads resolve every finding 007 path covered by this
matrix, including `pattern` and `propertyNames`, not only direct string length
bounds.

## Upstream tests

The affected upstream Python test file passed in both exact-head environments:

```text
PR #822: 545 passed in 8.05s
PR #828: 521 passed in 8.05s
```

Command shape:

```text
python -m pytest tests/python/test_json_schema_converter.py -q
```

## Process lesson

Duplicate search should precede deep characterization. Issue #800 and active
fix PRs already existed before this matrix was expanded. Searching first would
have focused the work immediately on fix validation and would have reduced
duplicated investigation.

Findings 001 through 006 have not received the same upstream duplicate audit.
That audit is recorded as pending work and was not performed in this scope.

## Issue comment

Published by `alk0x1` on issue #800:

https://github.com/mlc-ai/xgrammar/issues/800#issuecomment-5415618318

The published text is preserved below:

<!-- issue-comment-start -->
I ran an independent 32-code-point grid against the exact current heads of #822
and #828 to check whether the proposed fixes cover `pattern` and
`propertyNames`, not only direct string length bounds.

Exact heads tested:

- #822: `91d85b5f40e47214401751ecdec5d97ea978e6a5`
- #828: `e14ff8d92c8daef6931fc42a11ecb971e5dce3c4`

Each cell below is the number of invalid one-character inputs accepted out of
U+0000 through U+001F. Expected is 0. I checked both `accept_string` and
token-step acceptance with a three-entry custom vocabulary, then confirmed the
same result with GPT-2, Qwen 2.5, Mistral, and Llama 3 tokenizers.

| Build | `minLength` | `maxLength` | Both bounds | `pattern: ^.$` | `propertyNames` min | `propertyNames` max | `propertyNames` both |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stable 0.2.5 control | 30 | 30 | 30 | 32 | 30 | 30 | 30 |
| #822 head | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| #828 head | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

In stable 0.2.5, U+000A and U+000D are the only two labels still rejected by
the length-bounded path, while the one-character pattern accepts all 32. On
both PR heads, all 32 are rejected in every schema form above.

I also ran the affected upstream test file against each exact head:

- #822: `545 passed in 8.05s`
- #828: `521 passed in 8.05s`

Conclusion: in this matrix, both proposed fixes cover `pattern` and
`propertyNames` as well as direct `minLength` and `maxLength` paths.
<!-- issue-comment-end -->
