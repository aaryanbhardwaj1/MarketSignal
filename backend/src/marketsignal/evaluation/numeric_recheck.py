"""Independent numeric-faithfulness re-check of a stored answer (Phase 3, generalised in Phase 4).

The verifier reports what it dropped; this checks what it *kept*. Each unit's canonical
``[[HANDLE]]`` citations are resolved through the evidence API (the stored text, never the run's
pack), and every number in the unit is checked against the resolved parent texts with the same
support rule the verifier uses (``contract.unsupported_numbers``). Units without citations
(``[inference]`` and gap statements) are checked against the run's whole pack only when the pack
texts are supplied; the grounded harness's unsupported-claim rate uses cited units only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from marketsignal.generation import contract
from marketsignal.generation.types import CANONICAL_RE


class _EvidenceClient(Protocol):
    async def get(self, url: str) -> Any: ...


async def fetch_texts(client: _EvidenceClient, ws: str, handles: Iterable[str]) -> dict[str, str]:
    """Resolve handles through the workspace's evidence API; unresolvable handles are omitted."""
    out: dict[str, str] = {}
    for handle in sorted(set(handles)):
        response = await client.get(f"/api/workspaces/{ws}/evidence/{handle}")
        if response.status_code == 200:
            out[handle] = str(response.json().get("text", ""))
    return out


def units(content: str) -> list[tuple[str, str]]:
    sections = contract.parse_sections(content)
    return [(name, unit) for name, body in sections.items() for unit in contract.split_units(body)]


def recheck_content(
    content: str, texts: Mapping[str, str], pack: Iterable[str] | None = None
) -> dict[str, Any]:
    """Re-check every unit of ``content``.

    ``texts`` maps resolved handles to their parent text. A cited unit is *unsupported* when it
    contains a number absent from the texts of the handles it cites (an unresolvable citation
    contributes no text). With ``pack`` given, uncited units are checked against the pack texts
    (scope ``pack``); without it they are counted but not checked.
    """
    cited_all = set(CANONICAL_RE.findall(content))
    pack_values = (
        contract.number_values(texts[h] for h in pack if h in texts) if pack is not None else None
    )
    cited_units = uncited_units = 0
    unsupported: list[dict[str, Any]] = []
    for section, unit in units(content):
        handles = set(CANONICAL_RE.findall(unit))
        if handles:
            cited_units += 1
            values = contract.number_values(texts[h] for h in handles if h in texts)
            scope = "cited"
        else:
            uncited_units += 1
            if pack_values is None:
                continue
            values, scope = pack_values, "pack"
        missing = contract.unsupported_numbers(CANONICAL_RE.sub("", unit), values)
        if missing:
            unsupported.append(
                {
                    "section": section,
                    "scope": scope,
                    "numbers": [m.text for m in missing],
                    "unit": unit[:240],
                }
            )
    return {
        "cited_units": cited_units,
        "uncited_units": uncited_units,
        "unresolvable_citations": sorted(cited_all - set(texts)),
        "unsupported": unsupported,
    }
