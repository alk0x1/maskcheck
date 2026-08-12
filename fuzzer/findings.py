"""What a driver reports when an engine and the truth disagree."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Violation:
    kind: str  # "completeness" | "soundness" | "viability"
    engine: str
    tokenizer_id: str
    schema: dict
    instance: str
    detail: str
    token_index: int | None = None
    token_id: int | None = None
    token_text: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        where = ""
        if self.token_index is not None:
            where = (
                f" at token index {self.token_index}"
                f" (id={self.token_id}, {self.token_text!r})"
            )
        return (
            f"{self.kind} violation in {self.engine} on {self.tokenizer_id}{where}: "
            f"{self.detail}\n  schema:   {json.dumps(self.schema)}\n"
            f"  instance: {self.instance!r}"
        )
