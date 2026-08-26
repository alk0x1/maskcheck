"""Tokenizer loading and the one detail every driver depends on: how a token id
maps back to the text it contributes.

Engines are compiled against a tokenizer, so the tokenizer is part of every finding.
Keep the short ids stable: they are quoted verbatim in reproducers.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from transformers import AutoTokenizer, PreTrainedTokenizerBase

# Short id -> HF repo. Short ids appear in reproducers, so treat them as an API.
REGISTRY: dict[str, str] = {
    "gpt2": "openai-community/gpt2",
    "qwen2.5": "Qwen/Qwen2.5-0.5B-Instruct",
    "mistral": "mistralai/Mistral-7B-v0.1",
    "llama3": "Xenova/llama3-tokenizer",
}

REVISIONS: dict[str, str | None] = {
    "gpt2": "607a30d783dfa663caf39e06633721c8d4cfcd7e",
    "qwen2.5": "7ae557604adf67be50417f59c2c2f167def9a775",
    "mistral": "27d67f1b5f57dc0953326b2601d68371d40ea8da",
    "llama3": "72bff9ee09897a16b3b4b2b9995fecb0bfa7dbe6",
}


@dataclass(frozen=True)
class TokenizationEnumeration:
    tokenizations: tuple[tuple[int, ...], ...]
    states_examined: int
    truncated: bool


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

    def has_start_context_mismatch(self, text: str) -> bool:
        """Whether preceding model context changes the decoded generated text.

        SentencePiece/metaspace tokenizers can strip an initial word-boundary marker
        only when generated IDs are decoded in isolation. The same IDs after BOS then
        decode differently, so a standalone canonical tokenization is not enough to
        define model-generation behavior.
        """
        ids = self.encode(text)
        context_ids = self.encode("x")
        context = self.decode(context_ids)
        combined = self.hf.decode(
            [*context_ids, *ids],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        return not combined.startswith(context) or combined[len(context) :] != text

    def tokenizations(
        self,
        text: str,
        max_alternatives: int = 8,
        max_search_states: int = 4096,
    ) -> list[list[int]]:
        """Canonical encoding followed by bounded exact-roundtrip alternatives.

        Alternatives use tokens that decode to complete text in isolation. Byte
        fragments remain outside this string-level enumeration and are accounted for
        separately by the differential driver.
        """
        result = self.enumerate_tokenizations(
            text,
            max_alternatives=max_alternatives,
            max_search_states=max_search_states,
        )
        return [list(path) for path in result.tokenizations]

    @functools.lru_cache(maxsize=2048)
    def enumerate_tokenizations(
        self,
        text: str,
        max_alternatives: int = 8,
        max_search_states: int = 4096,
    ) -> TokenizationEnumeration:
        """Enumerate alternatives within an explicit search-state budget."""
        if max_alternatives < 0:
            raise ValueError("max_alternatives must be non-negative")
        if max_search_states < 1:
            raise ValueError("max_search_states must be positive")
        canonical = self.encode(text)
        output = [tuple(canonical)]
        seen = {tuple(canonical)}
        if max_alternatives == 0 or not text:
            return TokenizationEnumeration(tuple(output), 0, False)

        stack: list[tuple[int, tuple[int, ...]]] = [(0, ())]
        states_examined = 0
        while stack and len(output) <= max_alternatives:
            if states_examined >= max_search_states:
                return TokenizationEnumeration(
                    tuple(output), states_examined, truncated=True
                )
            position, path = stack.pop()
            states_examined += 1
            if position == len(text):
                if path not in seen and self.decode(list(path)) == text:
                    seen.add(path)
                    output.append(path)
                continue
            choices = self._tokens_by_initial.get(text[position], ())
            for piece, token_id in reversed(choices):
                if text.startswith(piece, position):
                    stack.append((position + len(piece), path + (token_id,)))
        return TokenizationEnumeration(tuple(output), states_examined, truncated=False)

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

    @functools.cached_property
    def _tokens_by_initial(self) -> dict[str, tuple[tuple[str, int], ...]]:
        grouped: dict[str, list[tuple[str, int]]] = {}
        for token_id, piece in enumerate(self.token_texts):
            if piece:
                grouped.setdefault(piece[0], []).append((piece, token_id))
        return {
            initial: tuple(sorted(entries, key=lambda item: (-len(item[0]), item[1])))
            for initial, entries in grouped.items()
        }


# Tokenizers named by a caller rather than pinned above, keyed by repo id. Kept apart
# from REGISTRY on purpose: that set is a published contract, quoted verbatim in every
# reproducer, and a run against someone else's tokenizer must not appear to extend it.
_EXTERNAL: dict[str, str | None] = {}


def repo_for(short_id: str) -> tuple[str, str | None]:
    """The Hugging Face repo and revision behind a tokenizer id."""
    if short_id in REGISTRY:
        return REGISTRY[short_id], REVISIONS[short_id]
    if short_id in _EXTERNAL:
        return short_id, _EXTERNAL[short_id]
    raise KeyError(
        f"unknown tokenizer {short_id!r}; registered: {sorted(REGISTRY)}"
    )


@functools.lru_cache(maxsize=None)
def load_tokenizer(short_id: str) -> Tokenizer:
    """Load a registered tokenizer. Cached: loading is slow and callers ask often."""
    repo, revision = repo_for(short_id)
    return Tokenizer(short_id, AutoTokenizer.from_pretrained(repo, revision=revision))


def resolve_tokenizer_id(name: str, revision: str | None = None) -> str:
    """Return the tokenizer id for a pinned short id or a Hugging Face repo id.

    The short ids above are pinned to a revision because they are quoted verbatim in
    reproducers and must not drift. Someone testing their own deployment needs their
    own tokenizer, which will not be one of them, so an unrecognised name is taken as
    a repo id for the Hub to resolve. Such an entry is unpinned unless ``revision`` is
    given, and a finding produced with one is only as reproducible as that repo.
    """
    if name in REGISTRY:
        return name
    _EXTERNAL.setdefault(name, revision)
    return name
