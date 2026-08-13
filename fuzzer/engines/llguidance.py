"""llguidance adapter using its low-level model-free matcher API."""

from __future__ import annotations

import functools
import json

import numpy as np
from llguidance import LLMatcher, LLTokenizer
from llguidance.hf import from_tokenizer

from fuzzer.engines.base import CapabilityGap, CompilationFailed
from fuzzer.tokenizers import load_tokenizer


@functools.lru_cache(maxsize=None)
def _tokenizer(tokenizer_id: str) -> LLTokenizer:
    wrapped = load_tokenizer(tokenizer_id)
    eos = wrapped.hf.eos_token_id
    if eos is None:
        raise CapabilityGap(f"{tokenizer_id} has no EOS token for llguidance")
    return from_tokenizer(
        wrapped.hf,
        n_vocab=wrapped.vocab_size,
        eos_token=eos,
        slices=LLTokenizer.json_slices(),
    )


@functools.lru_cache(maxsize=1024)
def _grammar(schema_json: str) -> str:
    return LLMatcher.grammar_from_json_schema(schema_json)


class LLGuidanceMatcher:
    def __init__(self, tokenizer: LLTokenizer, grammar: str):
        self._tokenizer = tokenizer
        self._eos_consumed = False
        self._matcher = LLMatcher(tokenizer, grammar, log_level=0)
        if self._matcher.is_error():
            raise CompilationFailed(self._matcher.get_error())

    def allowed_mask(self) -> set[int]:
        bias = np.frombuffer(self._matcher.compute_logit_bias(), dtype=np.uint8)
        return set(np.flatnonzero(bias == 200).tolist())

    def accept(self, token_id: int) -> bool:
        accepted = self._matcher.consume_token(token_id)
        if accepted and token_id in self._tokenizer.eos_tokens:
            self._eos_consumed = True
        return accepted

    def is_completed(self) -> bool:
        return self._matcher.is_accepting() and not self._matcher.is_error()

    def is_terminated(self) -> bool:
        return self._eos_consumed

    def can_stop(self) -> bool:
        return bool(set(self._tokenizer.eos_tokens) & self.allowed_mask())

    def reset(self) -> None:
        if not self._matcher.reset():
            raise RuntimeError("llguidance matcher refused to reset")
        self._eos_consumed = False


class LLGuidanceAdapter:
    name = "llguidance"

    def compile(self, schema: dict, tokenizer_id: str) -> LLGuidanceMatcher:
        tokenizer = _tokenizer(tokenizer_id)
        try:
            schema_json = json.dumps(schema, sort_keys=True, separators=(",", ":"))
            grammar = _grammar(schema_json)
            is_error, messages = LLMatcher.validate_grammar_with_warnings(
                grammar, tokenizer
            )
            if is_error:
                raise CompilationFailed(messages[0])
            return LLGuidanceMatcher(tokenizer, grammar)
        except CompilationFailed:
            raise
        except Exception as exc:
            raise CompilationFailed(f"llguidance rejected schema: {exc}") from exc
