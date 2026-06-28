"""Source-acquisition status for canonical LTM validation references."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiteratureReferenceStatus:
    """Current reproducibility status for one requested literature reference."""

    reference_id: str
    priority: int
    citation: str
    source_url: str
    status: str
    blocker: str
    next_step: str
    access_evidence: tuple[str, ...] = ()
    is_blocking_current_readiness: bool = True


def literature_reference_statuses() -> tuple[LiteratureReferenceStatus, ...]:
    """Return the current source-acquisition state for named references."""

    return (
        LiteratureReferenceStatus(
            reference_id="yperman_2007_thesis",
            priority=2,
            citation=(
                "Yperman, I. (2007). The link transmission model for dynamic "
                "network loading. Ph.D. thesis, Katolieke Universiteit Leuven."
            ),
            source_url="https://doi.org/10.1287/trsc.2013.0504",
            status="deferred_by_user",
            blocker=(
                "Deferred by user for the current canonical-validation pass after "
                "the source audit found no accessible numerically specified thesis "
                "scenario."
            ),
            next_step=(
                "Acquire the thesis text or a reviewed scenario excerpt with link "
                "parameters, demand, capacities, storage, and time-step convention."
            ),
            access_evidence=(
                "Crossref query for the exact thesis title returned later LTM references, "
                "not a primary thesis record with scenario data.",
                "KU Leuven Lirias search returned a JavaScript catalogue shell, not an "
                "extractable thesis record or numerical example.",
            ),
            is_blocking_current_readiness=False,
        ),
        LiteratureReferenceStatus(
            reference_id="de_souza_2025_mesoscopic_ltm",
            priority=3,
            citation=(
                "de Souza, F., Verbas, O., Auld, J., and Tampere, C. M. J. "
                "(2025). A mesoscopic link-transmission-model able to track "
                "individual vehicles. Simulation Modelling Practice and Theory."
            ),
            source_url="https://doi.org/10.1016/j.simpat.2025.103088",
            status="deferred_by_user",
            blocker=(
                "Deferred by user for the current canonical-validation pass after "
                "publisher endpoints did not expose a small numerical validation "
                "scenario without authorized full text."
            ),
            next_step=(
                "Review the full paper for the smallest reproducible link or "
                "network scenario before making any UC comparison claim."
            ),
            access_evidence=(
                "DOI resolution reaches the Elsevier article landing page.",
                "Elsevier text/plain API request returned HTTP 400 minimized metadata "
                "for unauthorized access.",
                "Elsevier text/xml API request returned HTTP 200 with zero content "
                "and an unauthorized minimized-metadata warning.",
            ),
            is_blocking_current_readiness=False,
        ),
    )
