"""Rendering a violation as a block that stands on its own.

Whoever reads one of these blocks is assumed to have neither this repository nor the
run that produced it. A block therefore repeats everything needed to judge the report:
which property failed, which build of which engine failed it, against which tokenizer,
at which step, and on which document. A block that says "completeness violation at
step 4" and nothing else is not a report, it is a note to self.

One rule about text. Engine findings are full of control characters, because that is
where the bugs are, and a raw control character written to a terminal either vanishes
or moves the cursor. Every character below U+0020 is therefore printed as its label,
never as itself, so that a block survives being copied into an issue tracker.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from fuzzer.findings import Violation

# Characters that must never reach the terminal as themselves. U+007F is included
# with the C0 range: it is equally invisible and equally likely to appear in a
# finding about string content.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_LABEL_WIDTH = 22


def render_text(value: str) -> str:
    """Quote ``value`` for display with every control character labelled.

    Backslash and double quote are escaped so the result reads as one token. Printable
    non-ASCII is left alone: a finding about a multi-byte character is easier to judge
    when the character is visible.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    labelled = _CONTROL.sub(lambda m: f"<U+{ord(m.group()):04X}>", escaped)
    return f'"{labelled}"'


def has_control_characters(*values: str | None) -> bool:
    """Whether any value would render a ``<U+00XX>`` label."""
    return any(_CONTROL.search(value) for value in values if value)


@dataclass(frozen=True)
class Occurrence:
    """One violation together with the schema file that produced it."""

    violation: Violation
    source: str


@dataclass
class CauseGroup:
    """Occurrences that share a root cause, in first-seen order."""

    key: tuple
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def first(self) -> Occurrence:
        return self.occurrences[0]

    @property
    def count(self) -> int:
        return len(self.occurrences)


def _normalise_reason(detail: str) -> str:
    """Strip the parts of a reason that vary with the witness, not with the cause.

    Reference validator messages quote the offending value and cite line and column
    numbers. Two witnesses failing the same way produce two different sentences, and
    grouping on the raw sentence would print one block per witness and bury the fact
    that there is a single bug behind them.
    """
    without_literals = re.sub(r"'[^']*'", "'...'", detail)
    return re.sub(r"\d+", "N", without_literals)


def cause_key(violation: Violation) -> tuple:
    """The identity a violation is deduplicated on."""
    return (
        violation.kind,
        violation.engine,
        violation.tokenizer_id,
        _normalise_reason(violation.detail),
        violation.token_text,
    )


def group_by_cause(occurrences: Iterable[Occurrence]) -> list[CauseGroup]:
    """Collapse occurrences to distinct causes, preserving discovery order."""
    groups: dict[tuple, CauseGroup] = {}
    for occurrence in occurrences:
        key = cause_key(occurrence.violation)
        groups.setdefault(key, CauseGroup(key)).occurrences.append(occurrence)
    return list(groups.values())


def _prefix_so_far(
    violation: Violation, decode: Callable[[Sequence[int]], str] | None
) -> str | None:
    """The text the engine had already accepted when it went wrong.

    The completeness driver records this directly for a blocked token. Everywhere else
    it has to be reconstructed from the accepted token ids, which needs the tokenizer,
    so callers without one get no prefix line rather than a guessed one.
    """
    context = violation.context
    if isinstance(context.get("prefix"), str):
        return context["prefix"]
    token_ids = context.get("token_ids")
    if not isinstance(token_ids, list) or decode is None:
        return None
    # token_index is None when the whole document was consumed and the engine then
    # disagreed about it being complete, so everything accepted is the prefix.
    end = len(token_ids) if violation.token_index is None else violation.token_index
    return decode(token_ids[:end])


def _token_role(kind: str) -> str:
    """What the reported token did wrong, in the words of the property it broke."""
    if kind == "completeness":
        return "blocked token"
    if kind == "soundness":
        return "wrongly allowed token"
    return "token"


def _line(label: str, value: str) -> str:
    return f"  {label.ljust(_LABEL_WIDTH)}{value}"


def render_block(
    group: CauseGroup,
    *,
    index: int,
    total: int,
    engine_version: str,
    decode: Callable[[Sequence[int]], str] | None = None,
) -> str:
    """Render one distinct cause as a self-contained block."""
    occurrence = group.first
    violation = occurrence.violation
    rule = "=" * 78
    lines = [
        rule,
        f"Cause {index} of {total}: {violation.kind} violation",
        rule,
        _line("property", violation.kind),
        _line("reason", violation.detail),
        _line("engine", f"{violation.engine} {engine_version}"),
        _line("tokenizer", violation.tokenizer_id),
        _line("schema source", occurrence.source),
    ]

    if group.count > 1:
        sources = sorted({item.source for item in group.occurrences})
        if len(sources) == 1:
            spread = f"{group.count}, all from this schema"
        else:
            shown = ", ".join(sources[:3]) + (" ..." if len(sources) > 3 else "")
            spread = f"{group.count} across {len(sources)} schemas ({shown})"
        lines.append(_line("occurrences", spread))

    step = "not reached" if violation.token_index is None else str(violation.token_index)
    lines.append(_line("step index", step))

    prefix = _prefix_so_far(violation, decode)
    if prefix is not None:
        lines.append(_line("prefix so far", render_text(prefix)))

    if violation.token_id is None:
        lines.append(_line(_token_role(violation.kind), "none, the failure is at the end"))
    else:
        text = "unavailable" if violation.token_text is None else render_text(violation.token_text)
        lines.append(
            _line(_token_role(violation.kind), f"id={violation.token_id} text={text}")
        )

    lines.append(_line("witness document", render_text(violation.instance)))
    lines.append(_line("schema", json.dumps(violation.schema, sort_keys=False)))

    if has_control_characters(prefix, violation.token_text, violation.instance):
        lines.append(
            _line("text convention", "characters below U+0020 are shown as <U+00XX>")
        )

    return "\n".join(lines)
