"""Outlines adapter using the model-free outlines-core DFA API."""

from __future__ import annotations

import functools
import json

from outlines_core import Guide, Index, Vocabulary
from outlines_core.json_schema import build_regex_from_schema

from fuzzer.engines.base import CapabilityGap, CompilationFailed
from fuzzer.tokenizers import REGISTRY, load_tokenizer


@functools.lru_cache(maxsize=None)
def _vocabulary(tokenizer_id: str) -> Vocabulary:
    try:
        return Vocabulary.from_pretrained(REGISTRY[tokenizer_id])
    except Exception as exc:
        raise CapabilityGap(
            f"outlines could not load tokenizer {tokenizer_id}: {exc}"
        ) from exc


@functools.lru_cache(maxsize=1024)
def _index(tokenizer_id: str, schema_json: str) -> Index:
    regex = build_regex_from_schema(schema_json)
    return Index(regex, _vocabulary(tokenizer_id))


class OutlinesMatcher:
    def __init__(self, index: Index, eos_token_id: int):
        self._guide = Guide(index)
        self._eos_token_id = eos_token_id
        self._eos_consumed = False

    def allowed_mask(self) -> set[int]:
        return set(self._guide.get_tokens())

    def accept(self, token_id: int) -> bool:
        if token_id not in self.allowed_mask():
            return False
        if token_id == self._eos_token_id and self._guide.is_finished():
            # outlines-core exposes EOS in a final state but deliberately has no EOS
            # DFA transition. Track the sampler-level stop locally.
            self._eos_consumed = True
            return True
        self._guide.advance(token_id, return_tokens=False)
        return True

    def is_completed(self) -> bool:
        return self._guide.is_finished()

    def is_terminated(self) -> bool:
        return self._eos_consumed

    def can_stop(self) -> bool:
        return self._eos_token_id in self.allowed_mask()

    def reset(self) -> None:
        self._guide.reset()
        self._eos_consumed = False


class OutlinesAdapter:
    name = "outlines"

    def compile(self, schema: dict, tokenizer_id: str) -> OutlinesMatcher:
        tok = load_tokenizer(tokenizer_id)
        eos = tok.hf.eos_token_id
        if eos is None:
            raise CapabilityGap(f"{tokenizer_id} has no EOS token for outlines")
        try:
            schema_json = json.dumps(schema, sort_keys=True, separators=(",", ":"))
            index = _index(tokenizer_id, schema_json)
            vocabulary_eos = _vocabulary(tokenizer_id).get_eos_token_id()
            if vocabulary_eos != eos:
                raise CapabilityGap(
                    f"outlines EOS {vocabulary_eos} != tokenizer EOS {eos}"
                )
            return OutlinesMatcher(index, eos)
        except CapabilityGap:
            raise
        except Exception as exc:
            raise CompilationFailed(f"outlines rejected schema: {exc}") from exc
