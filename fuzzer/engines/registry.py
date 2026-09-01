"""Looking up an engine adapter by name, without requiring it to be installed.

Each engine is a heavy optional dependency: xgrammar pulls in torch, outlines-core and
llguidance are compiled extensions. Someone testing one engine should not have to
install the other two, so nothing here imports an adapter until it is asked for, and a
missing engine is answered with an instruction rather than an ImportError traceback.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version


class EngineUnavailable(Exception):
    """A known engine is not importable in this environment."""


@dataclass(frozen=True)
class EngineSpec:
    name: str
    module: str
    adapter: str
    distribution: str  # the installed package whose version identifies the build
    extra: str  # the extra that installs it


SPECS: dict[str, EngineSpec] = {
    "xgrammar": EngineSpec(
        name="xgrammar",
        module="fuzzer.engines.xgrammar",
        adapter="XGrammarAdapter",
        distribution="xgrammar",
        extra="xgrammar",
    ),
    "llguidance": EngineSpec(
        name="llguidance",
        module="fuzzer.engines.llguidance",
        adapter="LLGuidanceAdapter",
        distribution="llguidance",
        extra="llguidance",
    ),
    "outlines": EngineSpec(
        name="outlines",
        module="fuzzer.engines.outlines",
        adapter="OutlinesAdapter",
        distribution="outlines-core",
        extra="outlines",
    ),
}

ENGINE_NAMES = tuple(SPECS)


def engine_version(name: str) -> str:
    """The installed version of the engine behind ``name``.

    Findings are version-specific, so an unknown version is reported as such rather
    than omitted: a reproducer that does not say which build it came from cannot be
    confirmed or dismissed by a maintainer.
    """
    try:
        return version(SPECS[name].distribution)
    except (KeyError, PackageNotFoundError):
        return "version unknown"


def is_available(name: str) -> bool:
    spec = SPECS.get(name)
    if spec is None:
        return False
    try:
        importlib.import_module(spec.module)
    except Exception:
        # Adapters fail to import for more reasons than a missing package: a broken
        # compiled extension raises too, and that is equally "cannot run here".
        return False
    return True


def availability() -> dict[str, str | None]:
    """Every known engine mapped to its version, or None when it cannot be imported."""
    return {
        name: engine_version(name) if is_available(name) else None
        for name in ENGINE_NAMES
    }


def describe_availability() -> str:
    """A one-line-per-engine summary for error messages."""
    lines = []
    for name, installed in availability().items():
        if installed is None:
            lines.append(f"  {name.ljust(12)}not installed")
        else:
            lines.append(f"  {name.ljust(12)}{installed}")
    return "\n".join(lines)


def load_engine(name: str):
    """Return an adapter instance for ``name``.

    Raises :class:`EngineUnavailable` with an actionable message, never an ImportError.
    """
    spec = SPECS.get(name)
    if spec is None:
        raise EngineUnavailable(
            f"unknown engine {name!r}. Known engines:\n{describe_availability()}"
        )
    try:
        module = importlib.import_module(spec.module)
    except Exception as exc:
        raise EngineUnavailable(
            f"engine {name!r} is not usable here: {exc}\n"
            f"Install it with: pip install 'maskcheck[{spec.extra}]'\n"
            f"Engines in this environment:\n{describe_availability()}"
        ) from exc
    return getattr(module, spec.adapter)()
