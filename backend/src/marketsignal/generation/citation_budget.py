"""Deterministic citation budget (Phase 5, A1): fit an over-cited answer under the cap.

List-style answers (enumerations, "top N" questions) tend to cite every source on every bullet
and then restate the same citations in the Answer section, so they exceed
``settings.verifier_max_citations`` and were refused (``too_many_citations`` on both attempts,
then the evidence-only fallback). This module runs on the *already verified* units, only when
the answer is over the cap, and removes citation markers in a fixed order. Verification is not
weakened:

* A unit never loses its last citation (a claim is never left uncited), and a citation is only
  removed when the unit's remaining citations still support every figure in it (the caller's
  ``supported`` check is the verifier's own numeric support rule).
* Conflicting-evidence bullets are never touched (each side must keep its citation).
* Every change is reported as a repair; nothing is silently dropped.

Order (each step stops as soon as the answer fits):

1. **Normalisation** - exact duplicates: a unit identical to an earlier unit of the same
   section is dropped; a second alias pointing at the same parent within one unit is dropped;
   a citation repeated from the previous unit of the same section is dropped from the later
   unit; an Answer sentence that restates a Key finding drops citations already carried by
   Key findings (the Answer reuses, not repeats, them).
2. **Extra citations** - units with more than one citation keep only their first supporting
   citation, lowest-value sections first (Interpretation, then Key findings, then Answer), and
   later units before earlier ones.
3. **Trailing findings** - Key-findings bullets beyond the first :data:`MIN_FINDINGS` are
   dropped from the end. This removes whole claims (never leaves one uncited).

If the answer is still over the cap, the verifier reports ``too_many_citations`` as before.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Final

from marketsignal.generation.contract import (
    ANSWER,
    FINDINGS,
    INTERPRETATION,
    SECTION_TITLES,
)

MIN_FINDINGS: Final = 3
# Sections whose extra citations are trimmed in step 2, lowest value first.
_TRIM_ORDER: Final = (INTERPRETATION, FINDINGS, ANSWER)
# Sections whose repeated adjacent citations are normalised in step 1.
_ADJACENT_SECTIONS: Final = (ANSWER, FINDINGS, INTERPRETATION)

Supported = Callable[[str, tuple[str, ...]], bool]


@dataclass(frozen=True, slots=True)
class Unit:
    """One verified answer unit (sentence or bullet)."""

    text: str  # still in alias form ("[E3]"); canonicalised at render time
    cited: tuple[str, ...]  # valid aliases, in order, unique
    inferred: bool
    gap: bool = False  # an evidence-gap statement (A5), rendered untagged


@dataclass(frozen=True, slots=True)
class BudgetOutcome:
    sections: dict[str, list[Unit]]
    repairs: tuple[str, ...]
    before: int  # citation markers before the budget ran
    after: int
    over_cited: tuple[str, ...]  # "E3 (5 times)" for aliases cited in more than one unit


def count(sections: Mapping[str, list[Unit]]) -> int:
    return sum(len(unit.cited) for units in sections.values() for unit in units)


def over_cited(sections: Mapping[str, list[Unit]]) -> tuple[str, ...]:
    """Aliases cited by more than one unit, most-cited first (ties by alias number)."""
    tally = Counter(alias for units in sections.values() for u in units for alias in u.cited)
    repeated = [(alias, n) for alias, n in tally.items() if n > 1]
    repeated.sort(key=lambda pair: (-pair[1], int(pair[0][1:])))
    return tuple(f"{alias} ({n} times)" for alias, n in repeated)


def _without(unit: Unit, alias: str) -> Unit:
    text = " ".join(unit.text.replace(f"[{alias}]", " ").split())
    return replace(unit, text=text, cited=tuple(a for a in unit.cited if a != alias))


class _Budget:
    def __init__(self, sections: Mapping[str, list[Unit]], cap: int, supported: Supported):
        self.sections = {key: list(units) for key, units in sections.items()}
        self.cap = cap
        self.supported = supported
        self.repairs: list[str] = []

    @property
    def over(self) -> bool:
        return count(self.sections) > self.cap

    def note(self, key: str, index: int, action: str) -> None:
        self.repairs.append(f"{SECTION_TITLES[key]} #{index}: {action} (citation cap {self.cap})")

    def drop(self, key: str, index: int, droppable: Iterable[str], why: str) -> bool:
        """Remove droppable aliases (last first) while the unit keeps >= 1 supporting citation.
        Returns False once the answer fits (callers stop)."""
        unit = self.sections[key][index]
        for alias in reversed([a for a in unit.cited if a in set(droppable)]):
            if not self.over:
                return False
            reduced = _without(unit, alias)
            if reduced.cited and self.supported(reduced.text, reduced.cited):
                unit = reduced
                self.sections[key][index] = unit
                self.note(key, index + 1, f"removed citation {alias}: {why}")
        return self.over

    def duplicate_units(self) -> None:
        for key, units in self.sections.items():
            seen: set[tuple[str, tuple[str, ...]]] = set()
            index = 0
            while index < len(units) and self.over:
                unit = units[index]
                ident = (unit.text, unit.cited)
                if unit.cited and ident in seen:
                    self.note(key, index + 1, "dropped a unit that repeats an earlier unit")
                    units.pop(index)  # the budget's own working copy
                    continue
                seen.add(ident)
                index += 1

    def same_parent(self, parents: Mapping[str, str]) -> None:
        for key, units in self.sections.items():
            for index, unit in enumerate(units):
                first: dict[str, str] = {}
                dupes = []
                for alias in unit.cited:
                    parent = parents.get(alias, alias)
                    if parent in first:
                        dupes.append(alias)
                    first.setdefault(parent, alias)
                if dupes and not self.drop(key, index, dupes, "same source as another citation"):
                    return

    def adjacent(self) -> None:
        for key in _ADJACENT_SECTIONS:
            units = self.sections.get(key, [])
            for index in range(1, len(units)):
                repeated = set(units[index - 1].cited)
                if not self.drop(key, index, repeated, "repeated from the previous unit"):
                    return

    def restated(self) -> None:
        in_findings = {a for unit in self.sections.get(FINDINGS, []) for a in unit.cited}
        for index in reversed(range(len(self.sections.get(ANSWER, [])))):
            if not self.drop(ANSWER, index, in_findings, "already cited in Key findings"):
                return

    def extras(self) -> None:
        for key in _TRIM_ORDER:
            for index in reversed(range(len(self.sections.get(key, [])))):
                cited = self.sections[key][index].cited
                if not self.drop(key, index, cited[1:] if cited else (), "extra citation"):
                    return

    def trailing_findings(self) -> None:
        units = self.sections.get(FINDINGS, [])
        while self.over and len(units) > MIN_FINDINGS:
            self.note(FINDINGS, len(units), "dropped a trailing Key findings bullet")
            units.pop()


def fit_citations(
    sections: Mapping[str, list[Unit]],
    cap: int,
    *,
    supported: Supported,
    parents: Mapping[str, str],
) -> BudgetOutcome:
    """Return ``sections`` unchanged when within ``cap``; otherwise apply the ordered steps in
    the module docstring until the answer fits (or nothing more may be removed).

    ``supported(text, cited)`` must be the verifier's support check for a cited unit;
    ``parents`` maps alias -> canonical parent handle.
    """
    before = count(sections)
    repeated = over_cited(sections)
    budget = _Budget(sections, cap, supported)
    steps: tuple[Callable[[], None], ...] = (
        budget.duplicate_units,
        lambda: budget.same_parent(parents),
        budget.adjacent,
        budget.restated,
        budget.extras,
        budget.trailing_findings,
    )
    for step in steps:
        if not budget.over:
            break
        step()
    result = {key: units for key, units in budget.sections.items() if units}
    return BudgetOutcome(result, tuple(budget.repairs), before, count(result), repeated)
