"""Tokenizer loading and the one detail every driver depends on: how a token id
maps back to the text it contributes.

Engines are compiled against a tokenizer, so the tokenizer is part of every finding.
Keep the short ids stable: they are quoted verbatim in reproducers.
"""

from __future__ import annotations

import functools

from transformers import AutoTokenizer, PreTrainedTokenizerBase

# Short id -> HF repo. Short ids appear in reproducers, so treat them as an API.
REGISTRY: dict[str, str] = {
    "gpt2": "gpt2",
}


class Tokenizer:
    """Thin wrapper pinning down the encode/decode conventions the drivers assume.

    Two conventions matter and both are easy to get silently wrong:

    - ``encode`` never adds special tokens. The grammar describes the JSON text, not
      the chat scaffolding around it, so a BOS token prepended by the tokenizer would
      show up as a spurious completeness violation at index 0.
    - ``decode_token`` decodes a single id in isolation. This is not always the same
      as that id's contribution inside a longer sequence (byte-level BPE tokenizers
      can split a multi-byte character across ids), so it is for reporting and
      assertions, not for reconstructing strings. Use ``decode`` for that.
    """

    def __init__(self, short_id: str, hf: PreTrainedTokenizerBase) -> None:
        self.id = short_id
        self.hf = hf

    @property
    def vocab_size(self) -> int:
        # len() includes added/special tokens; tokenizer.vocab_size does not, and a
        # bitmask sized by the smaller number would index out of range.
        return len(self.hf)

    def encode(self, text: str) -> list[int]:
        return self.hf.encode(text, add_special_tokens=False)

    def decode(self, token_ids: list[int]) -> str:
        return self.hf.decode(token_ids, skip_special_tokens=False)

    def decode_token(self, token_id: int) -> str:
        return self.hf.decode([token_id], skip_special_tokens=False)

    @functools.cached_property
    def token_texts(self) -> list[str | None]:
        """Per-token text, or None where the token is not comparable as text.

        Two kinds of token are excluded, and both exclusions are counted by callers
        rather than hidden:

        - Special tokens. ``decode`` renders them as their literal spelling
          (``<|endoftext|>``), which is not text the model is emitting into the JSON.
        - Byte-level fragments. In byte-level BPE a multi-byte character can be split
          across two tokens, so neither piece is valid UTF-8 on its own and ``decode``
          returns U+FFFD. A string-level oracle cannot judge those; a byte-level one
          could, and that is a known limitation of this harness rather than a
          property of the engines.
        """
        special = set(self.hf.all_special_ids)
        texts: list[str | None] = []
        for token_id in range(self.vocab_size):
            if token_id in special:
                texts.append(None)
                continue
            text = self.decode_token(token_id)
            texts.append(None if "�" in text else text)
        return texts


@functools.lru_cache(maxsize=None)
def load_tokenizer(short_id: str) -> Tokenizer:
    """Load a registered tokenizer. Cached: loading is slow and callers ask often."""
    try:
        repo = REGISTRY[short_id]
    except KeyError:
        raise KeyError(
            f"unknown tokenizer {short_id!r}; registered: {sorted(REGISTRY)}"
        ) from None
    return Tokenizer(short_id, AutoTokenizer.from_pretrained(repo))
