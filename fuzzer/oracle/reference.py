"""Reference token-level acceptor.

Deliberately naive, written for obvious correctness rather than speed. It holds the
decoded string so far and accepts a candidate token iff ``prefix + decode(token)``
is a viable prefix of some string in the schema's language.

The design that makes this trustworthy:

    every positive verdict is certified by a witness.

``viable_prefix`` does not merely reason that a completion exists, it constructs one
and runs it through the reference validator. So a false "viable" is impossible unless
``jsonschema`` itself is wrong. That moves the entire correctness burden onto the
negative side: the parser must not miss a viable completion. Every place where it
might is either handled explicitly or raises :class:`Unsupported`, never silently
returns "not viable".

Where the parser cannot reason about a construct at all -- ``pattern``, ``allOf``,
``not``, ``if``/``then`` -- it raises :class:`Unsupported`. A capability gap recorded
honestly is worth more than a confident wrong answer from the oracle.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator

from fuzzer.oracle.validator import validate_text


class Unsupported(Exception):
    """The reference cannot reason about this schema construct.

    Not a violation and not a verdict: the caller must skip the case and record a
    capability gap.
    """


# Keywords that change which instances are valid and that the parser does not model.
# Meeting one of these means the oracle must abstain rather than guess.
_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "pattern", "patternProperties", "allOf", "not", "if", "then", "else",
        "dependentSchemas", "dependentRequired", "unevaluatedProperties",
        "unevaluatedItems", "propertyNames", "contains", "multipleOf",
        "exclusiveMinimum", "exclusiveMaximum", "uniqueItems", "format",
    }
)

_NUMBER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
# Deliberately loose: this only prunes the completion search, so over-approximating
# costs time while under-approximating would lose witnesses. Err loose.
_NUMBER_PREFIX_RE = re.compile(r"-?(?:0|[1-9][0-9]*)?(?:\.[0-9]*)?(?:[eE][+-]?[0-9]*)?")
_NUMBER_CHARS = "0123456789.eE+-"
_WS = " \t\n\r"


@dataclass(frozen=True)
class Done:
    """A complete value of the schema occupies ``text[start:end]``."""

    end: int


@dataclass(frozen=True)
class Open:
    """``text`` ran out mid-value; appending ``completion`` finishes this value."""

    completion: str


Outcome = Done | Open


@dataclass(frozen=True)
class Viability:
    viable: bool
    witness: str | None = None
    complete: bool = False
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.viable


class Reference:
    """Character-level prefix oracle for one schema."""

    def __init__(
        self,
        schema: dict,
        max_depth: int = 12,
        allow_surrounding_whitespace: bool = False,
    ) -> None:
        self.schema = schema
        self.root = schema
        self.max_depth = max_depth
        # RFC 8259 permits whitespace around a JSON text, so a literal reading makes a
        # leading space viable for every schema. No engine allows it: they all treat
        # the constrained region as exactly the document. Reporting that as a
        # completeness violation on every case would bury the real findings under
        # thousands of identical ones, so the default is the engines' reading. Interior
        # whitespace is still checked, which is how the CR finding surfaced.
        self.allow_surrounding_whitespace = allow_surrounding_whitespace
        _assert_supported(schema)

    # ---- public API ----

    def viable_prefix(self, text: str) -> Viability:
        """Whether ``text`` is a prefix of some document valid against the schema."""
        if not self.allow_surrounding_whitespace and text[:1] in tuple(_WS):
            return Viability(False, reason="leading whitespace outside the document")

        candidates: list[str] = []
        for outcome in self._value(self.schema, text, 0, 0):
            if isinstance(outcome, Open):
                candidates.append(text + outcome.completion)
            elif self.allow_surrounding_whitespace:
                if _only_ws(text, outcome.end):
                    candidates.append(text)
            elif outcome.end == len(text):
                candidates.append(text)

        for witness in candidates:
            if validate_text(self.schema, witness):
                return Viability(True, witness=witness, complete=witness == text)
        if candidates:
            # The parser proposed completions and every one failed validation. That is
            # a parser gap, not evidence of non-viability, so refuse to answer.
            raise Unsupported(
                f"proposed completions for {text!r} did not validate: {candidates!r}"
            )
        return Viability(False, reason=f"no completion of {text!r} matches the schema")

    def is_complete(self, text: str) -> bool:
        return bool(validate_text(self.schema, text))

    # ---- parser ----

    def _value(self, schema: Any, text: str, pos: int, depth: int) -> Iterator[Outcome]:
        if depth > self.max_depth:
            raise Unsupported(f"recursion deeper than max_depth={self.max_depth}")
        schema = self._resolve(schema)

        if schema is True or schema == {}:
            schema = {}
        if schema is False:
            return

        pos = _skip_ws(text, pos)
        if pos >= len(text):
            # The value is entirely absent: any minimal instance completes it.
            yield Open(self._minimal(schema, depth))
            return

        if "enum" in schema or "const" in schema:
            values = schema["enum"] if "enum" in schema else [schema["const"]]
            yield from _literals(values, text, pos)
            return

        types = schema.get("type")
        if types is None:
            types = ["object", "array", "string", "number", "boolean", "null"]
        elif isinstance(types, str):
            types = [types]

        for branch in schema.get("anyOf", []) + schema.get("oneOf", []):
            # Union over branches. For a positive verdict this is an over-approximation,
            # which the witness check catches. For a negative verdict it is exact: if no
            # branch can parse the text, no branch can complete it either.
            yield from self._value(branch, text, pos, depth + 1)
        if "anyOf" in schema or "oneOf" in schema:
            return

        ch = text[pos]
        for typ in types:
            if typ == "object" and ch == "{":
                yield from self._object(schema, text, pos, depth)
            elif typ == "array" and ch == "[":
                yield from self._array(schema, text, pos, depth)
            elif typ == "string" and ch == '"':
                yield from self._string(schema, text, pos)
            elif typ in ("number", "integer") and (ch == "-" or ch.isdigit()):
                yield from self._number(schema, text, pos)
            elif typ == "boolean":
                yield from _literals([True, False], text, pos)
            elif typ == "null":
                yield from _literals([None], text, pos)

    def _string(self, schema: dict, text: str, pos: int) -> Iterator[Outcome]:
        min_len = schema.get("minLength", 0)
        max_len = schema.get("maxLength")
        i = pos + 1  # past the opening quote
        n_chars = 0
        while i < len(text):
            c = text[i]
            if c == '"':
                if n_chars >= min_len:
                    yield Done(i + 1)
                return
            if c == "\\":
                esc = _escape_tail(text, i)
                if esc is None:
                    return  # malformed escape: no valid document has this prefix
                if isinstance(esc, str):
                    # Text ended inside the escape; `esc` finishes it.
                    yield Open(esc + _pad(min_len - n_chars - 1) + '"')
                    return
                i = esc
            elif c in "\x00\x1f":
                return  # control characters must be escaped in JSON strings
            else:
                i += 1
            n_chars += 1
            if max_len is not None and n_chars > max_len:
                return
        # Ran out of text inside the string.
        yield Open(_pad(min_len - n_chars) + '"')

    def _number(self, schema: dict, text: str, pos: int) -> Iterator[Outcome]:
        match = _NUMBER_RE.match(text, pos)
        if match and match.end() > pos and self._number_ok(schema, match.group()):
            yield Done(match.end())
        # The rest of the text may be a proper prefix of a longer number: `1e` needs a
        # digit, and `1` needs another one when the schema says minimum 10.
        tail = text[pos:]
        if _NUMBER_PREFIX_RE.fullmatch(tail):
            completion = self._number_completion(schema, tail)
            if completion is not None:
                yield Open(completion)

    def _number_completion(
        self, schema: dict, tail: str, max_extra: int = 4, max_nodes: int = 4096
    ) -> str | None:
        """Shortest suffix making ``tail`` a valid number, or None if there is none.

        Breadth-first over digits and exponent punctuation, pruned to strings that are
        still plausibly a number prefix, so the usual one- or two-character witness is
        found almost immediately and unbounded numeric schemas cost nothing.

        The two ways of failing are not the same and are not conflated:

        - The tree was fully explored because pruning killed every branch. No number
          has this prefix at all, so None is a definite answer.
        - A branch was cut off by ``max_extra`` or ``max_nodes``. Then the answer is
          unknown, because a bound like ``minimum: 100000`` needs a longer suffix and
          an exponent can move a number in either direction, so no cheap monotonicity
          argument closes the gap. That raises :class:`Unsupported`, since reporting
          non-viability here would turn an oracle limitation into a phantom violation
          against the engine.
        """
        queue: list[str] = [""]
        nodes = 0
        truncated = False
        while queue:
            extra = queue.pop(0)
            nodes += 1
            if nodes > max_nodes:
                raise Unsupported(
                    f"numeric completion search for {tail!r} exceeded {max_nodes} nodes"
                )
            candidate = tail + extra
            if extra and _NUMBER_RE.fullmatch(candidate) and self._number_ok(schema, candidate):
                return extra
            children = [
                extra + ch
                for ch in _NUMBER_CHARS
                if _NUMBER_PREFIX_RE.fullmatch(tail + extra + ch)
            ]
            if len(extra) < max_extra:
                queue.extend(children)
            elif children:
                truncated = True

        if truncated:
            raise Unsupported(
                f"no numeric completion for {tail!r} within {max_extra} extra characters"
            )
        return None

    def _number_ok(self, schema: dict, literal: str) -> bool:
        try:
            value = json.loads(literal)
        except json.JSONDecodeError:
            return False
        if schema.get("type") == "integer" and not float(value).is_integer():
            return False
        if "minimum" in schema and value < schema["minimum"]:
            return False
        if "maximum" in schema and value > schema["maximum"]:
            return False
        return True

    def _object(self, schema: dict, text: str, pos: int, depth: int) -> Iterator[Outcome]:
        props: dict = schema.get("properties", {})
        required: list[str] = list(schema.get("required", []))
        extra = schema.get("additionalProperties", True)
        if extra not in (True, False):
            raise Unsupported("additionalProperties as a schema")
        yield from self._members(schema, props, required, extra, text, pos + 1, depth, set(), True)

    def _members(
        self, schema, props, required, extra, text, pos, depth, seen, first
    ) -> Iterator[Outcome]:
        """Parse object members from ``pos``, having already consumed ``seen`` keys."""
        pos = _skip_ws(text, pos)
        if pos >= len(text):
            yield Open(self._finish_object(props, required, seen, extra, depth, first))
            return

        if text[pos] == "}":
            if set(required) <= seen:
                yield Done(pos + 1)
            return

        if not first:
            if text[pos] != ",":
                return
            pos = _skip_ws(text, pos + 1)
            if pos >= len(text):
                tail = self._members_tail(props, required, seen, extra, depth)
                if tail is not None:
                    yield Open(tail)
                return

        if text[pos] != '"':
            return

        for key, end, remainder in self._keys(props, extra, seen, text, pos):
            if end is None:
                # Partial key: finish the key, give it a value, then close the object.
                sub = props.get(key, {})
                rest = self._finish_object(props, required, seen | {key}, extra, depth, False)
                yield Open(remainder + '":' + self._minimal(sub, depth + 1) + rest)
                continue
            after = _skip_ws(text, end)
            if after >= len(text):
                rest = self._finish_object(props, required, seen | {key}, extra, depth, False)
                yield Open(":" + self._minimal(props.get(key, {}), depth + 1) + rest)
                continue
            if text[after] != ":":
                continue
            for outcome in self._value(props.get(key, {}), text, after + 1, depth + 1):
                if isinstance(outcome, Open):
                    rest = self._finish_object(props, required, seen | {key}, extra, depth, False)
                    yield Open(outcome.completion + rest)
                else:
                    yield from self._members(
                        schema, props, required, extra, text, outcome.end, depth, seen | {key}, False
                    )

    def _members_tail(self, props, required, seen, extra, depth) -> str | None:
        """Completion for text ending right after a comma: one more member, then close.

        Returns None when no member can follow, which is a definite non-viability
        rather than a gap: with additionalProperties false and every declared key
        already used, a comma has nothing legal after it.
        """
        for key in list(required) + list(props):
            if key not in seen:
                body = json.dumps(key) + ":" + self._minimal(props.get(key, {}), depth + 1)
                return body + self._finish_object(props, required, seen | {key}, extra, depth, False)
        if extra is not False:
            return '"z":null}'
        return None

    def _finish_object(self, props, required, seen, extra, depth, first) -> str:
        """Text that closes an object, supplying every still-missing required key."""
        parts = []
        for key in required:
            if key not in seen:
                parts.append(json.dumps(key) + ":" + self._minimal(props.get(key, {}), depth + 1))
        sep = "" if first or not parts else ","
        return sep + ",".join(parts) + "}"

    def _keys(self, props, extra, seen, text, pos) -> Iterator[tuple[str, int | None, str]]:
        """Candidate keys matching the string literal starting at ``pos``.

        Yields ``(key, end, "")`` for a fully consumed key, or ``(key, None, tail)``
        when the text ends part-way through it, where ``tail`` is the rest of the key
        literal up to but not including its closing quote.
        """
        raw = text[pos:]
        candidates = [k for k in props if k not in seen]
        if extra is not False and "z" not in candidates:
            candidates = candidates + ["z"]
        for key in candidates:
            for literal in _key_literals(key):
                if raw == literal:
                    # Text ends exactly at the closing quote, which is still missing.
                    yield key, None, ""
                elif raw.startswith(literal + '"'):
                    # +1 for the closing quote. Requiring it is what stops key "a" from
                    # matching the text `"ab"`.
                    yield key, pos + len(literal) + 1, ""
                elif literal.startswith(raw):
                    yield key, None, literal[len(raw) :]
                else:
                    continue
                break

    def _array(self, schema: dict, text: str, pos: int, depth: int) -> Iterator[Outcome]:
        items = schema.get("items", {})
        min_items = schema.get("minItems", 0)
        yield from self._elements(items, min_items, schema.get("maxItems"), text, pos + 1, depth, 0)

    def _elements(self, items, min_items, max_items, text, pos, depth, count) -> Iterator[Outcome]:
        pos = _skip_ws(text, pos)
        if pos >= len(text):
            yield Open(self._finish_array(items, min_items, depth, count, first=count == 0))
            return
        if text[pos] == "]":
            if count >= min_items:
                yield Done(pos + 1)
            return
        if count > 0:
            if text[pos] != ",":
                return
            pos = _skip_ws(text, pos + 1)
            if pos >= len(text):
                yield Open(self._minimal(items, depth + 1) + self._finish_array(items, min_items, depth, count + 1, first=False))
                return
        if max_items is not None and count >= max_items:
            return
        for outcome in self._value(items, text, pos, depth + 1):
            if isinstance(outcome, Open):
                yield Open(outcome.completion + self._finish_array(items, min_items, depth, count + 1, first=False))
            else:
                yield from self._elements(items, min_items, max_items, text, outcome.end, depth, count + 1)

    def _finish_array(self, items, min_items, depth, count, first) -> str:
        parts = [self._minimal(items, depth + 1) for _ in range(max(0, min_items - count))]
        sep = "" if first or not parts else ","
        return sep + ",".join(parts) + "]"

    # ---- minimal instances ----

    def _minimal(self, schema: Any, depth: int) -> str:
        """Shortest text this harness knows how to write for ``schema``."""
        if depth > self.max_depth:
            raise Unsupported(f"minimal instance deeper than max_depth={self.max_depth}")
        schema = self._resolve(schema)
        if schema is True or schema is False or schema == {}:
            return "null" if schema is not False else _unsatisfiable()

        if "const" in schema:
            return json.dumps(schema["const"])
        if "enum" in schema:
            return json.dumps(schema["enum"][0])
        for branch in schema.get("anyOf", []) + schema.get("oneOf", []):
            return self._minimal(branch, depth + 1)

        typ = schema.get("type")
        if isinstance(typ, list):
            typ = typ[0]
        if typ == "string":
            return json.dumps("a" * schema.get("minLength", 0))
        if typ in ("number", "integer"):
            lo, hi = schema.get("minimum"), schema.get("maximum")
            value = 0 if lo is None else int(lo) if float(lo).is_integer() else lo
            if hi is not None and value > hi:
                raise Unsupported(f"unsatisfiable numeric bounds {lo}..{hi}")
            return json.dumps(value)
        if typ == "boolean":
            return "true"
        if typ == "null" or typ is None:
            return "null"
        if typ == "object":
            props = schema.get("properties", {})
            required = schema.get("required", [])
            body = ",".join(
                json.dumps(k) + ":" + self._minimal(props.get(k, {}), depth + 1) for k in required
            )
            return "{" + body + "}"
        if typ == "array":
            items = schema.get("items", {})
            body = ",".join(self._minimal(items, depth + 1) for _ in range(schema.get("minItems", 0)))
            return "[" + body + "]"
        raise Unsupported(f"cannot build a minimal instance for type {typ!r}")

    def _resolve(self, schema: Any) -> Any:
        seen = 0
        while isinstance(schema, dict) and "$ref" in schema:
            ref = schema["$ref"]
            if not ref.startswith("#/"):
                raise Unsupported(f"non-local $ref {ref!r}")
            target: Any = self.root
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                target = target[part]
            schema = target
            seen += 1
            if seen > self.max_depth:
                raise Unsupported("$ref chain too long")
        if isinstance(schema, dict):
            _assert_supported(schema)
        return schema


# ---- helpers ----


def _assert_supported(schema: Any) -> None:
    if not isinstance(schema, dict):
        return
    bad = _UNSUPPORTED_KEYWORDS & schema.keys()
    if bad:
        raise Unsupported(f"unsupported keyword(s): {sorted(bad)}")


def _unsatisfiable() -> str:
    raise Unsupported("schema `false` has no instances")


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in _WS:
        pos += 1
    return pos


def _only_ws(text: str, pos: int) -> bool:
    return _skip_ws(text, pos) >= len(text)


def _pad(n: int) -> str:
    return "a" * max(0, n)


def _literals(values: list, text: str, pos: int) -> Iterator[Outcome]:
    """Match ``text[pos:]`` against the JSON spellings of fixed values."""
    for value in values:
        for literal in _spellings(value):
            raw = text[pos:]
            if raw.startswith(literal):
                yield Done(pos + len(literal))
                break
            if literal.startswith(raw):
                yield Open(literal[len(raw) :])
                break


def _spellings(value: Any) -> list[str]:
    """JSON spellings of a value that a generator might plausibly emit.

    Non-ASCII can be written literally or escaped, and both are the same document, so
    a reference that knew only one spelling would report phantom violations.
    """
    out = [json.dumps(value, ensure_ascii=False)]
    escaped = json.dumps(value, ensure_ascii=True)
    if escaped != out[0]:
        out.append(escaped)
    return out


def _key_literals(key: str) -> list[str]:
    """Spellings of an object key, without the closing quote.

    The closing quote is excluded so a partial key like ``"ab`` can be recognised as a
    prefix of both ``ab`` and ``abc``.
    """
    return [s[:-1] for s in _spellings(key)]


_SHORT_ESCAPES = '"\\/bfnrt'


def _escape_tail(text: str, i: int) -> int | str | None:
    """Resolve the escape sequence at ``text[i] == '\\\\'``.

    Returns the index just past it, or the string that would finish a truncated one,
    or None if it is malformed.
    """
    if i + 1 >= len(text):
        return 'n'  # `\` alone: `\n` is the shortest legal completion
    c = text[i + 1]
    if c in _SHORT_ESCAPES:
        return i + 2
    if c != "u":
        return None
    digits = text[i + 2 : i + 6]
    if len(digits) < 4:
        if not all(d in "0123456789abcdefABCDEF" for d in digits):
            return None
        return "0" * (4 - len(digits))
    if not all(d in "0123456789abcdefABCDEF" for d in digits):
        return None
    return i + 6
