"""Random JSON Schemas biased toward constrained-decoding boundary cases."""

from __future__ import annotations

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

KEYS = ("a", "ab", "abc", "v", "n", "s", "é", "日")
STRING_VALUES = ("", "a", "x", "alpha", "alphabet", "é", "日本語", "🙂")
NUMBER_BOUNDS = (-100, -10, -1.5, -1, 0, 1, 1.5, 10, 20, 100)


@st.composite
def _string_schemas(draw) -> dict:
    minimum = draw(st.integers(min_value=0, max_value=4))
    maximum = draw(st.one_of(st.none(), st.integers(min_value=minimum, max_value=8)))
    schema: dict = {"type": "string"}
    if minimum:
        schema["minLength"] = minimum
    if maximum is not None:
        schema["maxLength"] = maximum
    return schema


@st.composite
def _numeric_schemas(draw, numeric_type: str) -> dict:
    bounds = (
        tuple(bound for bound in NUMBER_BOUNDS if isinstance(bound, int))
        if numeric_type == "integer"
        else NUMBER_BOUNDS
    )
    first = draw(st.sampled_from(bounds))
    second = draw(st.sampled_from(bounds))
    lower, upper = sorted((first, second))
    bound_kind = draw(st.sampled_from(("none", "minimum", "maximum", "both")))
    schema: dict = {"type": numeric_type}
    if bound_kind in ("minimum", "both"):
        schema["minimum"] = lower
    if bound_kind in ("maximum", "both"):
        schema["maximum"] = upper
    return schema


def _leaf_schemas() -> SearchStrategy[dict]:
    enum = st.sampled_from(
        (
            {"enum": ["alpha", "alphabet", "alphabetical"]},
            {"enum": ["a", "ab", "abc"]},
            {"enum": [0, 1, -1]},
        )
    )
    const = st.sampled_from(STRING_VALUES + (True, False, None, 0, 1)).map(
        lambda value: {"const": value}
    )
    return st.one_of(
        _string_schemas(),
        _numeric_schemas("integer"),
        _numeric_schemas("number"),
        st.just({"type": "boolean"}),
        st.just({"type": "null"}),
        enum,
        const,
    )


@st.composite
def _object_schemas(draw, values: SearchStrategy[dict]) -> dict:
    properties = draw(
        st.dictionaries(st.sampled_from(KEYS), values, min_size=0, max_size=4)
    )
    keys = list(properties)
    required = draw(st.lists(st.sampled_from(keys), unique=True)) if keys else []
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


@st.composite
def _array_schemas(draw, values: SearchStrategy[dict]) -> dict:
    minimum = draw(st.integers(min_value=0, max_value=3))
    maximum = draw(st.integers(min_value=minimum, max_value=4))
    return {
        "type": "array",
        "items": draw(values),
        "minItems": minimum,
        "maxItems": maximum,
    }


def schemas(max_depth: int = 3) -> SearchStrategy[dict]:
    """Schemas supported by the reference oracle, capped at ``max_depth`` nesting."""
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    leaves = _leaf_schemas()
    if max_depth == 0:
        return leaves

    children = schemas(max_depth - 1)
    any_of = st.lists(children, min_size=2, max_size=3).map(
        lambda branches: {"anyOf": branches}
    )
    # Repeating leaves weights the distribution away from giant trees while keeping
    # nested arrays, objects, and shared-prefix unions common enough to shrink well.
    return st.one_of(
        leaves,
        leaves,
        _object_schemas(children),
        _array_schemas(children),
        any_of,
    )
