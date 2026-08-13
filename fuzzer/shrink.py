"""Predicate-driven discovery and shrinking of generated conformance failures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from hypothesis import find, settings

from fuzzer.generators.instances import schema_instance_pairs

FailurePredicate = Callable[[dict, str], bool]


@dataclass(frozen=True)
class MinimalCase:
    schema: dict
    instance: str

    def reproducer(self) -> str:
        """A compact starting point for a standalone upstream reproducer."""
        schema = json.dumps(self.schema, ensure_ascii=False, separators=(",", ":"))
        return f"schema = {schema}\ninstance = {self.instance!r}"


def find_minimal(
    fails: FailurePredicate,
    *,
    max_depth: int = 3,
    max_examples: int = 10_000,
) -> MinimalCase:
    """Find and shrink a generated pair for which ``fails(schema, instance)`` is true."""
    schema, instance = find(
        schema_instance_pairs(max_depth=max_depth),
        lambda pair: fails(*pair),
        settings=settings(
            max_examples=max_examples,
            deadline=None,
            database=None,
            derandomize=True,
        ),
    )
    return MinimalCase(schema=schema, instance=instance)
