"""``get_evidence``: resolve up to 8 canonical handles through the evidence resolver, with a
per-item miss reason (``MALFORMED`` / ``NOT_FOUND`` / ``SOURCE_DELETED``) and truncated text.

A handle into another workspace, an analytic handle, a passage above the run's maximum
confidentiality or outside the token's class claim is ``NOT_FOUND`` (indistinguishable from
absent: no existence leak). That includes purged versions: ``SOURCE_DELETED`` is reported only
when the purged version's confidentiality and class are themselves visible to the run."""

from __future__ import annotations

from marketsignal.db.session import scoped_session
from marketsignal.evidence.handles import MalformedHandleError
from marketsignal.evidence.resolver import (
    EvidenceDeletedError,
    EvidenceNotFoundError,
    resolve_evidence,
)
from marketsignal.retrieval.types import allowed_confidentiality
from marketsignal.tools.contracts import (
    TRUNCATED,
    GetEvidenceIn,
    GetEvidenceOut,
    ResolvedEvidence,
)
from marketsignal.tools.env import ToolEnv
from marketsignal.tools.impl.common import truncate

TEXT_MAX_CHARS = 1200


async def get_evidence(env: ToolEnv, args: GetEvidenceIn) -> GetEvidenceOut:
    allowed = set(allowed_confidentiality(env.max_confidentiality))
    items: list[ResolvedEvidence] = []
    clipped = False
    async with scoped_session(env.factory, env.scope) as session:
        for handle in dict.fromkeys(args.handles):  # de-duplicated, order kept
            item, cut = await _one(session, env, handle, allowed)
            items.append(item)
            clipped = clipped or cut
    return GetEvidenceOut(items=items, warnings=[TRUNCATED] if clipped else [])


async def _one(
    session: object, env: ToolEnv, handle: str, allowed: set[str]
) -> tuple[ResolvedEvidence, bool]:
    try:
        resolved = await resolve_evidence(session, env.scope, handle)  # type: ignore[arg-type]
    except MalformedHandleError:
        return ResolvedEvidence(handle=handle, found=False, miss_reason="MALFORMED"), False
    except EvidenceDeletedError as exc:
        tomb = exc.tombstone
        visible = tomb.confidentiality in allowed and env.class_allowed(tomb.source_class)
        reason = "SOURCE_DELETED" if visible else "NOT_FOUND"
        return ResolvedEvidence(handle=handle, found=False, miss_reason=reason), False
    except EvidenceNotFoundError:
        return ResolvedEvidence(handle=handle, found=False, miss_reason="NOT_FOUND"), False
    if resolved.source["confidentiality"] not in allowed or not env.class_allowed(
        str(resolved.source["source_class"])
    ):
        return ResolvedEvidence(handle=handle, found=False, miss_reason="NOT_FOUND"), False
    body, cut = truncate(resolved.text, TEXT_MAX_CHARS)
    return (
        ResolvedEvidence(
            handle=resolved.handle,
            found=True,
            text=body,
            locator_label=resolved.locator_label,
            source_title=str(resolved.source["title"]),
            source_class=resolved.source["source_class"],
        ),
        cut,
    )
