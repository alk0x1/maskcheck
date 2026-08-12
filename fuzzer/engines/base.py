"""The uniform engine interface.

If an engine cannot support one of these operations, that is recorded as a capability
gap (raise ``CapabilityGap``), not worked around. A worked-around gap turns into a
finding that says more about the adapter than about the engine.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class CapabilityGap(Exception):
    """An engine cannot express something the harness needs.

    Distinct from a violation: it means "cannot test this here", not "engine is wrong".
    """


class CompilationFailed(Exception):
    """The engine refused to compile a schema the reference validator accepts.

    Also not a violation by itself. Some engines document unsupported JSON Schema
    keywords, and the sweep records those separately from correctness bugs.
    """


@runtime_checkable
class Matcher(Protocol):
    """A compiled grammar advanced one token at a time."""

    def allowed_mask(self) -> set[int]:
        """Token ids legal in the current state."""

    def accept(self, token_id: int) -> bool:
        """Advance the state. Returns False if the token was rejected."""

    def is_completed(self) -> bool:
        """Whether the tokens accepted so far form a complete valid string.

        This, not :meth:`is_terminated`, is the right end-of-instance check for a
        valid document: it does not require a stop token to have been emitted.
        """

    def is_terminated(self) -> bool:
        """Whether the matcher will accept no further tokens (stop token consumed)."""

    def can_stop(self) -> bool:
        """Whether a stop token is legal right now.

        A grammar can be 'completed' while the engine still refuses to let the model
        emit EOS. Generation then cannot end, which is a real failure and a distinct
        one, so the harness keeps the two signals apart.
        """

    def reset(self) -> None:
        """Return to the initial state."""


@runtime_checkable
class EngineAdapter(Protocol):
    name: str

    def compile(self, schema: dict, tokenizer_id: str) -> Matcher:
        """Compile a JSON Schema against a registered tokenizer."""
