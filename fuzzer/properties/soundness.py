"""Random-walk soundness driver for completed engine outputs."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from fuzzer.engines.base import EngineAdapter
from fuzzer.findings import Violation
from fuzzer.oracle.validator import validate_text
from fuzzer.tokenizers import load_tokenizer


@dataclass
class SoundnessResult:
    walks_requested: int
    max_steps: int
    seed: int
    walks_started: int = 0
    walks_completed: int = 0
    walks_inconclusive: int = 0
    tokens_accepted: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def check_soundness(
    engine: EngineAdapter,
    schema: dict,
    tokenizer_id: str,
    *,
    walks: int = 100,
    max_steps: int = 64,
    seed: int = 0,
) -> SoundnessResult:
    """Walk engine masks and validate every completed decoded document."""
    if walks < 1 or max_steps < 1:
        raise ValueError("walks and max_steps must be positive")

    tok = load_tokenizer(tokenizer_id)
    special = set(tok.hf.all_special_ids)
    rng = random.Random(seed)
    result = SoundnessResult(walks_requested=walks, max_steps=max_steps, seed=seed)

    for walk in range(walks):
        result.walks_started += 1
        matcher = engine.compile(schema, tokenizer_id)
        token_ids: list[int] = []

        for _ in range(max_steps + 1):
            completed = matcher.is_completed() and matcher.can_stop()
            if completed and rng.choice((True, False)):
                _record_completion(
                    result, engine, schema, tokenizer_id, tok, token_ids, walk
                )
                break
            if len(token_ids) >= max_steps:
                if completed:
                    _record_completion(
                        result, engine, schema, tokenizer_id, tok, token_ids, walk
                    )
                else:
                    result.walks_inconclusive += 1
                break

            allowed = sorted(matcher.allowed_mask() - special)
            if not allowed:
                if completed:
                    _record_completion(
                        result, engine, schema, tokenizer_id, tok, token_ids, walk
                    )
                else:
                    result.walks_inconclusive += 1
                break
            token_id = rng.choice(allowed)
            if not matcher.accept(token_id):
                result.walks_inconclusive += 1
                break
            token_ids.append(token_id)
            result.tokens_accepted += 1

    return result


def _record_completion(result, engine, schema, tokenizer_id, tok, token_ids, walk):
    result.walks_completed += 1
    text = tok.decode(token_ids)
    validation = validate_text(schema, text)
    if validation:
        return
    result.violations.append(
        Violation(
            kind="soundness",
            engine=engine.name,
            tokenizer_id=tokenizer_id,
            schema=schema,
            instance=text,
            detail=f"engine completed invalid output: {validation.reason}",
            token_index=len(token_ids) - 1 if token_ids else None,
            token_id=token_ids[-1] if token_ids else None,
            token_text=tok.decode_token(token_ids[-1]) if token_ids else None,
            context={"walk": walk, "token_ids": list(token_ids)},
        )
    )
