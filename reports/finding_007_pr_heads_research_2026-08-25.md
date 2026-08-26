# Finding 007: XGrammar PR head research

Captured from official GitHub repository, pull request, and Actions sources on
2026-08-25. This note records inputs for testing the two proposed fixes. It does
not report results from running either branch.

## Exact revisions

| PR | Status | Head repository | Head ref | Head SHA | Base |
| --- | --- | --- | --- | --- | --- |
| [#822](https://github.com/mlc-ai/xgrammar/pull/822) | Open, non-draft, unmerged; GitHub reports `mergeable_state: blocked` | `SyaOtiLan/xgrammar` | `fix/json-schema-string-length-escapes` | [`91d85b5f40e47214401751ecdec5d97ea978e6a5`](https://github.com/mlc-ai/xgrammar/commit/91d85b5f40e47214401751ecdec5d97ea978e6a5) | `mlc-ai/xgrammar:main`, PR API base SHA `1819601ee311e48787ff32b2a27aa53b3835d313` |
| [#828](https://github.com/mlc-ai/xgrammar/pull/828) | Open, non-draft, unmerged | `filipsajdak/xgrammar` | `fix/escape-in-length-bounded-string` | [`e14ff8d92c8daef6931fc42a11ecb971e5dce3c4`](https://github.com/mlc-ai/xgrammar/commit/e14ff8d92c8daef6931fc42a11ecb971e5dce3c4) | `mlc-ai/xgrammar:main`, PR API base SHA `53da3ff8c0db359ecb6d4b41f154308c82a89aaf` |

The fields above come directly from the current [#822 PR API](https://api.github.com/repos/mlc-ai/xgrammar/pulls/822)
and [#828 PR API](https://api.github.com/repos/mlc-ai/xgrammar/pulls/828).
The base SHAs are the values reported by each PR record, not an independent
inspection of current `main`.

## Stated scope

PR #822 says it fixes the dedicated `minLength` and `maxLength` string path by
preserving JSON escape spellings, counting a complete escape as one character,
and excluding unescaped U+0000 through U+001F. Its body says the `pattern` path
already uses a JSON-string-aware expression. That `pattern` statement is the
author's claim, not a result independently verified in this research. The body
does not mention `propertyNames`. See the [PR description](https://github.com/mlc-ai/xgrammar/pull/822).

PR #828 describes two commits in the bounded-string path. The first adds JSON
escape alternatives and excludes unescaped U+0000 through U+001F. The second
counts code points consistently across raw and escaped spellings and rejects
unpaired surrogate escapes in that bounded path. It explicitly says the
unbounded path is unchanged and identifies its first commit as equivalent to
#822. It does not claim a `pattern` or `propertyNames` fix. See the
[#828 description](https://github.com/mlc-ai/xgrammar/pull/828) and its
[exact-head commit](https://github.com/mlc-ai/xgrammar/commit/e14ff8d92c8daef6931fc42a11ecb971e5dce3c4).

## Changed files and tests

Both PRs change only `cpp/json_schema_converter.cc` and
`tests/python/test_json_schema_converter.py`, according to the official
[#822 files API](https://api.github.com/repos/mlc-ai/xgrammar/pulls/822/files)
and [#828 files API](https://api.github.com/repos/mlc-ai/xgrammar/pulls/828/files).

PR #822 changes the length-constrained branch in `GenerateString` and adds six
focused test groups. They cover accepted JSON escapes, escape length accounting,
rejection of unescaped U+0000 through U+001F, non-BMP length accounting,
rejection of unpaired surrogate escapes under bounds, and preservation of the
unbounded behavior. See the exact-head
[converter source](https://github.com/mlc-ai/xgrammar/blob/91d85b5f40e47214401751ecdec5d97ea978e6a5/cpp/json_schema_converter.cc#L2368)
and [tests](https://github.com/mlc-ai/xgrammar/blob/91d85b5f40e47214401751ecdec5d97ea978e6a5/tests/python/test_json_schema_converter.py#L2427).
The PR body reports local test and formatting results. Those are author-reported,
not GitHub CI results.

PR #828 also changes the length-constrained branch in `GenerateString`. Its
tests cover escape acceptance, surrogate-pair counting, and rejection of lone
surrogates. See the exact-head
[converter source](https://github.com/mlc-ai/xgrammar/blob/e14ff8d92c8daef6931fc42a11ecb971e5dce3c4/cpp/json_schema_converter.cc#L2368)
and [tests](https://github.com/mlc-ai/xgrammar/blob/e14ff8d92c8daef6931fc42a11ecb971e5dce3c4/tests/python/test_json_schema_converter.py#L2411).
Its body reports 547 converter tests passing. That is also author-reported,
not GitHub CI evidence.

Neither PR adds an explicit `pattern` or `propertyNames` test. Therefore the
changed files and stated tests do not answer whether either exact head fixes
those finding 007 schema forms.

## Official source build path

The documentation present at both exact heads gives the same Python source
build procedure: clone recursively, install `pre-commit`, copy
`cmake/config.cmake` to the repository root, install `scikit-build-core` and
`apache-tvm-ffi`, then install the project editable with
`python3 -m pip install --no-build-isolation -e .`. It also documents
`python3 -m pip install ".[test]"` followed by either the complete pytest run or
the subset that excludes tests requiring a Hugging Face token. See the exact
[#822 installation document](https://github.com/SyaOtiLan/xgrammar/blob/91d85b5f40e47214401751ecdec5d97ea978e6a5/docs/start/installation.md#method-2-build-xgrammar-python-package-from-source)
and [#828 installation document](https://github.com/filipsajdak/xgrammar/blob/e14ff8d92c8daef6931fc42a11ecb971e5dce3c4/docs/start/installation.md#method-2-build-xgrammar-python-package-from-source).

To test the revisions identified above, the checkout must be pinned to the full
head SHA in the table before following that source-build procedure. The source
repositories and refs are taken from the PR API records.

## Exact-head artifacts

No official downloadable exact-head wheel or other Actions artifact was found
for either SHA.

- For #822, the upstream repository has four pull-request workflow runs at the
  exact SHA. All completed with `action_required`. The
  [wheel workflow run](https://github.com/mlc-ai/xgrammar/actions/runs/32749391300)
  has zero jobs and its [artifact listing](https://api.github.com/repos/mlc-ai/xgrammar/actions/runs/32749391300/artifacts)
  is empty. The fork has no Actions run at that exact SHA.
- For #828, the upstream repository also has four pull-request workflow runs at
  the exact SHA, all completed with `action_required`. The
  [wheel workflow run](https://github.com/mlc-ai/xgrammar/actions/runs/32747493585)
  has zero jobs and its [artifact listing](https://api.github.com/repos/mlc-ai/xgrammar/actions/runs/32747493585/artifacts)
  is empty. The fork has no Actions run at that exact SHA.

The repository's exact-head
[build workflow](https://github.com/filipsajdak/xgrammar/blob/e14ff8d92c8daef6931fc42a11ecb971e5dce3c4/.github/workflows/build_and_release.yaml)
would normally build and upload wheels as workflow artifacts, but those jobs did
not start for these pull-request runs. Testing therefore requires a source build
unless new official artifacts appear later.
