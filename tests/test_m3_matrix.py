"""Minimal end-to-end probe of every M3 engine/tokenizer cell."""

import pytest

from fuzzer.engines.llguidance import LLGuidanceAdapter
from fuzzer.engines.outlines import OutlinesAdapter
from fuzzer.engines.xgrammar import XGrammarAdapter
from fuzzer.properties.completeness import check_completeness

SCHEMA = {"const": "x"}
INSTANCE = '"x"'
ENGINES = (XGrammarAdapter(), LLGuidanceAdapter(), OutlinesAdapter())
TOKENIZERS = ("gpt2", "qwen2.5", "mistral", "llama3")


@pytest.mark.parametrize("engine", ENGINES, ids=lambda engine: engine.name)
@pytest.mark.parametrize("tokenizer_id", TOKENIZERS)
def test_every_m3_cell_compiles_and_exposes_known_context_behavior(
    engine, tokenizer_id
):
    result = check_completeness(engine, SCHEMA, INSTANCE, tokenizer_id)

    if tokenizer_id == "mistral":
        assert len(result.violations) == 1
        assert result.violations[0].token_index == 0
    else:
        assert result.violations == []
