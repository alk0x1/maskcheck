"""What a violation block must contain to be actionable on its own."""

from __future__ import annotations

from fuzzer.findings import Violation
from fuzzer.report import (
    CauseGroup,
    Occurrence,
    cause_key,
    group_by_cause,
    render_block,
    render_text,
)

SCHEMA = {"type": "string", "maxLength": 1}


def violation(**overrides) -> Violation:
    fields = dict(
        kind="completeness",
        engine="xgrammar",
        tokenizer_id="gpt2",
        schema=SCHEMA,
        instance='"x"',
        detail="valid instance rejected: token not in allowed mask",
        token_index=1,
        token_id=87,
        token_text="x",
        context={"token_ids": [1, 87, 1], "prefix": '"'},
    )
    fields.update(overrides)
    return Violation(**fields)


def block(occurrences, **overrides) -> str:
    group = CauseGroup(key=cause_key(occurrences[0].violation), occurrences=list(occurrences))
    options = dict(index=1, total=1, engine_version="0.2.4", decode=None)
    options.update(overrides)
    return render_block(group, **options)


def test_control_characters_are_labelled_never_emitted_raw():
    rendered = render_text("a\nb\tc\x00d\x1be")
    assert "\n" not in rendered
    assert "\t" not in rendered
    assert "\x00" not in rendered
    assert "\x1b" not in rendered
    assert "<U+000A>" in rendered
    assert "<U+0009>" in rendered
    assert "<U+0000>" in rendered
    assert "<U+001B>" in rendered


def test_delete_is_labelled_too():
    assert render_text("a\x7f") == '"a<U+007F>"'


def test_printable_non_ascii_survives_unescaped():
    # A finding about a multi-byte character is only judgeable if the character shows.
    assert render_text("é日🙂") == '"é日🙂"'


def test_quotes_and_backslashes_stay_unambiguous():
    assert render_text('a"b\\c') == '"a\\"b\\\\c"'


def test_block_carries_every_field_a_reader_needs():
    rendered = block([Occurrence(violation(), "schemas/label.json")])
    assert "completeness" in rendered
    assert "xgrammar 0.2.4" in rendered  # engine and its version
    assert "gpt2" in rendered  # tokenizer
    assert "schemas/label.json" in rendered  # where the schema came from
    assert "step index            1" in rendered  # step index
    assert 'prefix so far         "\\""' in rendered  # prefix so far
    assert "blocked token         id=87" in rendered  # the offending token
    assert 'witness document      "\\"x\\""' in rendered  # the witness
    assert '"maxLength": 1' in rendered  # the schema itself


def test_block_names_the_token_role_per_property():
    assert "blocked token" in block([Occurrence(violation(), "s.json")])
    unsound = violation(kind="soundness", detail="engine completed invalid output: bad")
    assert "wrongly allowed token" in block([Occurrence(unsound, "s.json")])


def test_text_convention_line_appears_only_when_a_label_was_emitted():
    plain = block([Occurrence(violation(), "s.json")])
    assert "text convention" not in plain
    control = block([Occurrence(violation(instance='"\x10"'), "s.json")])
    assert "text convention" in control


def test_prefix_is_reconstructed_from_token_ids_when_not_recorded():
    # Soundness records no prefix, so the block has to rebuild it from the walk.
    unsound = violation(
        kind="soundness",
        context={"token_ids": [10, 20, 30]},
        token_index=2,
    )
    rendered = block(
        [Occurrence(unsound, "s.json")],
        decode=lambda ids: "".join(str(i) for i in ids),
    )
    assert 'prefix so far         "1020"' in rendered


def test_no_prefix_line_rather_than_a_guessed_one():
    unsound = violation(kind="soundness", context={"token_ids": [10, 20]}, token_index=1)
    assert "prefix so far" not in block([Occurrence(unsound, "s.json")], decode=None)


def test_witnesses_differing_only_in_the_quoted_value_are_one_cause():
    first = violation(kind="soundness", detail="at /: 'aaaa' is too long", token_text=None)
    second = violation(kind="soundness", detail="at /: 'bbbbbb' is too long", token_text=None)
    assert cause_key(first) == cause_key(second)


def test_different_blocked_tokens_are_different_causes():
    assert cause_key(violation(token_text="x")) != cause_key(violation(token_text=":"))


def test_grouping_preserves_discovery_order_and_counts():
    occurrences = [
        Occurrence(violation(token_text="x"), "a.json"),
        Occurrence(violation(token_text=":"), "b.json"),
        Occurrence(violation(token_text="x"), "c.json"),
    ]
    groups = group_by_cause(occurrences)
    assert len(groups) == 2
    assert groups[0].count == 2
    assert groups[0].first.source == "a.json"
    assert groups[1].count == 1


def test_block_reports_spread_across_schemas():
    occurrences = [
        Occurrence(violation(), "a.json"),
        Occurrence(violation(), "b.json"),
    ]
    assert "2 across 2 schemas" in block(occurrences)
