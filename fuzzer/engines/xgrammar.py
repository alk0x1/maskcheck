"""XGrammar adapter."""

from __future__ import annotations

import functools

import numpy as np
import xgrammar as xgr

from fuzzer.engines.base import CompilationFailed
from fuzzer.tokenizers import load_tokenizer


@functools.lru_cache(maxsize=None)
def _tokenizer_info(tokenizer_id: str) -> tuple[xgr.TokenizerInfo, int]:
    """Build XGrammar's view of a tokenizer. Cached: this walks the whole vocab."""
    tok = load_tokenizer(tokenizer_id)
    info = xgr.TokenizerInfo.from_huggingface(tok.hf, vocab_size=tok.vocab_size)
    return info, tok.vocab_size


@functools.lru_cache(maxsize=None)
def _compiler(tokenizer_id: str) -> xgr.GrammarCompiler:
    info, _ = _tokenizer_info(tokenizer_id)
    return xgr.GrammarCompiler(info)


def _bitmask_to_set(bitmask: np.ndarray, vocab_size: int) -> set[int]:
    """Decode XGrammar's packed bitmask into the set of allowed token ids.

    The bitmask is int32 words, token id ``i`` living at bit ``i % 32`` of word
    ``i // 32``. Viewing the words as bytes and unpacking little-endian reproduces
    exactly that ordering, but only on a little-endian host, so assert rather than
    silently return a permuted vocabulary.
    """
    if np.little_endian is not True:  # pragma: no cover - no big-endian CI host
        raise RuntimeError("bitmask decoding assumes a little-endian host")
    bits = np.unpackbits(bitmask.view(np.uint8), bitorder="little")
    return set(np.flatnonzero(bits[:vocab_size]).tolist())


class XGrammarMatcher:
    def __init__(self, compiled: xgr.CompiledGrammar, vocab_size: int, stop_tokens: set[int]):
        self._compiled = compiled
        self._vocab_size = vocab_size
        self._stop_tokens = stop_tokens
        self._matcher = xgr.GrammarMatcher(compiled)
        self._bitmask = xgr.allocate_token_bitmask(1, vocab_size)

    def allowed_mask(self) -> set[int]:
        self._matcher.fill_next_token_bitmask(self._bitmask)
        return _bitmask_to_set(self._bitmask[0].numpy(), self._vocab_size)

    def accept(self, token_id: int) -> bool:
        return self._matcher.accept_token(token_id)

    def is_completed(self) -> bool:
        return self._matcher.is_completed()

    def is_terminated(self) -> bool:
        return self._matcher.is_terminated()

    def can_stop(self) -> bool:
        return bool(self._stop_tokens & self.allowed_mask())

    def reset(self) -> None:
        self._matcher.reset()


class XGrammarAdapter:
    name = "xgrammar"

    def compile(self, schema: dict, tokenizer_id: str) -> XGrammarMatcher:
        info, vocab_size = _tokenizer_info(tokenizer_id)
        try:
            compiled = _compiler(tokenizer_id).compile_json_schema(schema)
        except Exception as exc:  # xgrammar raises assorted types for bad schemas
            raise CompilationFailed(f"xgrammar rejected schema: {exc}") from exc
        return XGrammarMatcher(compiled, vocab_size, set(info.stop_token_ids or []))
