"""M3 engine/tokenizer/property matrix runner and coverage-honest report."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from collections.abc import Callable

from hypothesis import given, seed as hypothesis_seed, settings

from fuzzer.engines.base import CapabilityGap, CompilationFailed, EngineAdapter
from fuzzer.findings import Violation
from fuzzer.generators.instances import schema_instance_pairs
from fuzzer.oracle.reference import Unsupported
from fuzzer.oracle.validator import check_schema, validate_text
from fuzzer.properties.completeness import check_completeness_variants
from fuzzer.properties.soundness import check_soundness
from fuzzer.properties.viability import check_viability
from fuzzer.tokenizers import load_tokenizer


@dataclass(frozen=True)
class SweepConfig:
    completeness_max_alternatives: int = 8
    completeness_max_search_states: int = 4096
    soundness_walks: int = 100
    soundness_max_steps: int = 64
    viability_lookahead_depth: int = 4
    viability_max_candidates: int = 32
    viability_max_branching: int = 64
    seed: int = 0


@dataclass
class PropertyStats:
    cases_run: int = 0
    checks_completed: int = 0
    inconclusive_checks: int = 0
    capability_gaps: int = 0
    compilation_gaps: int = 0
    alternative_checks: int = 0
    canonical_failures_with_accepted_alternative: int = 0
    gap_details: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)


@dataclass
class SweepCell:
    engine: str
    tokenizer_id: str
    tokenizer_context_sensitive: bool = False
    completeness: PropertyStats = field(default_factory=PropertyStats)
    soundness: PropertyStats = field(default_factory=PropertyStats)
    viability: PropertyStats = field(default_factory=PropertyStats)

    @property
    def all_violations(self) -> list[Violation]:
        return [
            *self.completeness.violations,
            *self.soundness.violations,
            *self.viability.violations,
        ]

    @property
    def violation_counts(self) -> dict[str, int]:
        return {
            "completeness": len(self.completeness.violations),
            "soundness": len(self.soundness.violations),
            "viability": len(self.viability.violations),
        }


@dataclass
class SweepReport:
    config: SweepConfig
    pairs_requested: int
    cells: list[SweepCell]

    def to_markdown(self) -> str:
        lines = [
            "# M3 sweep report",
            "",
            "## Configuration",
            "",
            "| Parameter | Value |",
            "|---|---:|",
            f"| Schema-instance pairs | {self.pairs_requested} |",
            (
                "| Completeness alternate tokenizations | "
                f"{self.config.completeness_max_alternatives} |"
            ),
            (
                "| Completeness search-state limit | "
                f"{self.config.completeness_max_search_states} |"
            ),
            f"| Soundness walks per schema | {self.config.soundness_walks} |",
            f"| Soundness maximum tokens | {self.config.soundness_max_steps} |",
            (
                "| Viability lookahead depth | "
                f"{self.config.viability_lookahead_depth} |"
            ),
            (
                "| Viability candidates per step | "
                f"{self.config.viability_max_candidates} |"
            ),
            f"| Viability branch limit | {self.config.viability_max_branching} |",
            f"| Seed | {self.config.seed} |",
            "",
            "## Matrix",
            "",
            (
                "| Engine | Tokenizer | Property | Cases | Decidable checks | "
                "Inconclusive | Capability gaps | Compilation gaps | Violations |"
            ),
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for cell in self.cells:
            for name in ("completeness", "soundness", "viability"):
                stats: PropertyStats = getattr(cell, name)
                lines.append(
                    f"| {cell.engine} | {cell.tokenizer_id} | {name} | "
                    f"{stats.cases_run} | {stats.checks_completed} | "
                    f"{stats.inconclusive_checks} | {stats.capability_gaps} | "
                    f"{stats.compilation_gaps} | {len(stats.violations)} |"
                )
        context_sensitive = sorted(
            {cell.tokenizer_id for cell in self.cells if cell.tokenizer_context_sensitive}
        )
        if context_sensitive:
            lines.extend(
                [
                    "",
                    "## Tokenizer context warnings",
                    "",
                    (
                        "Standalone canonical tokenization is context-sensitive for: "
                        + ", ".join(context_sensitive)
                        + ". Completeness records at the initial token require separate "
                        "classification and are not independent engine findings."
                    ),
                ]
            )
        return "\n".join(lines) + "\n"


def generate_pairs(
    *, count: int, max_depth: int = 3, seed: int = 0
) -> list[tuple[dict, str]]:
    """Collect a deterministic Hypothesis stream for a reproducible sweep."""
    if count < 1:
        raise ValueError("count must be positive")
    output: list[tuple[dict, str]] = []

    @hypothesis_seed(seed)
    @settings(max_examples=count, deadline=None, database=None)
    @given(schema_instance_pairs(max_depth=max_depth))
    def collect(pair):
        output.append(pair)

    collect()
    return output


def run_sweep(
    *,
    engines: list[EngineAdapter],
    tokenizer_ids: list[str],
    pairs: list[tuple[dict, str]],
    config: SweepConfig | None = None,
    on_cell_complete: Callable[[SweepCell], None] | None = None,
) -> SweepReport:
    """Run all three M3 properties over an engine/tokenizer matrix."""
    config = config or SweepConfig()
    _validate_pairs(pairs)
    cells: list[SweepCell] = []

    for engine in engines:
        for tokenizer_id in tokenizer_ids:
            tokenizer = load_tokenizer(tokenizer_id)
            cell = SweepCell(
                engine=engine.name,
                tokenizer_id=tokenizer_id,
                tokenizer_context_sensitive=any(
                    tokenizer.has_start_context_mismatch(instance)
                    for _, instance in pairs
                ),
            )
            for index, (schema, instance) in enumerate(pairs):
                _run_completeness(
                    cell,
                    engine,
                    schema,
                    instance,
                    tokenizer_id,
                    config,
                )
                _run_soundness(
                    cell,
                    engine,
                    schema,
                    tokenizer_id,
                    replace(config, seed=config.seed + index),
                )
                _run_viability(
                    cell,
                    engine,
                    schema,
                    instance,
                    tokenizer_id,
                    replace(config, seed=config.seed + index),
                )
            cells.append(cell)
            if on_cell_complete is not None:
                on_cell_complete(cell)

    return SweepReport(config=config, pairs_requested=len(pairs), cells=cells)


def _validate_pairs(pairs):
    for schema, instance in pairs:
        schema_result = check_schema(schema)
        instance_result = validate_text(schema, instance)
        if not schema_result:
            raise ValueError(schema_result.reason)
        if not instance_result:
            raise ValueError(f"invalid generated pair {instance!r}: {instance_result.reason}")


def _run_completeness(cell, engine, schema, instance, tokenizer_id, config):
    stats = cell.completeness
    try:
        result = check_completeness_variants(
            engine,
            schema,
            instance,
            tokenizer_id,
            max_alternatives=config.completeness_max_alternatives,
            max_search_states=config.completeness_max_search_states,
        )
    except (CapabilityGap, Unsupported) as exc:
        _gap(stats, exc, compilation=False)
        return
    except CompilationFailed as exc:
        _gap(stats, exc, compilation=True)
        return
    stats.cases_run += 1
    stats.checks_completed += len(result.all_results)
    stats.alternative_checks += len(result.alternatives)
    stats.canonical_failures_with_accepted_alternative += int(
        result.canonical_failed_with_accepted_alternative
    )
    stats.inconclusive_checks += int(result.enumeration_truncated)
    stats.violations.extend(result.canonical.violations)


def _run_soundness(cell, engine, schema, tokenizer_id, config):
    stats = cell.soundness
    try:
        result = check_soundness(
            engine,
            schema,
            tokenizer_id,
            walks=config.soundness_walks,
            max_steps=config.soundness_max_steps,
            seed=config.seed,
        )
    except (CapabilityGap, Unsupported) as exc:
        _gap(stats, exc, compilation=False)
        return
    except CompilationFailed as exc:
        _gap(stats, exc, compilation=True)
        return
    stats.cases_run += 1
    stats.checks_completed += result.walks_completed
    stats.inconclusive_checks += result.walks_inconclusive
    stats.violations.extend(result.violations)


def _run_viability(cell, engine, schema, instance, tokenizer_id, config):
    stats = cell.viability
    try:
        result = check_viability(
            engine,
            schema,
            instance,
            tokenizer_id,
            lookahead_depth=config.viability_lookahead_depth,
            max_candidates=config.viability_max_candidates,
            max_branching=config.viability_max_branching,
            seed=config.seed,
        )
    except (CapabilityGap, Unsupported) as exc:
        _gap(stats, exc, compilation=False)
        return
    except CompilationFailed as exc:
        _gap(stats, exc, compilation=True)
        return
    stats.cases_run += 1
    stats.checks_completed += (
        result.viable_candidates + len(result.violations)
    )
    stats.inconclusive_checks += result.inconclusive_candidates
    stats.violations.extend(result.violations)


def _gap(stats, exc, *, compilation):
    if compilation:
        stats.compilation_gaps += 1
    else:
        stats.capability_gaps += 1
    stats.gap_details.append(str(exc))
