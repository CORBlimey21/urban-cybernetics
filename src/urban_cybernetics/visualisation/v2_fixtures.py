"""Sanctioned persisted V2 acceptance fixture generation."""

from __future__ import annotations

from pathlib import Path

from .orchestrator import RunOrchestrator
from .persistence import ArtifactRepository
from .v2_contract import RunLifecycleState, RunRequestV2


SIOUX_FALLS_BOUNDED_RUN_ID = "v2-sioux-falls-bounded-100-v1"


def write_bounded_sioux_falls_fixture(root: Path) -> Path:
    """Execute, validate, exact-replay, and persist the 100-packet V2 fixture."""

    repository = ArtifactRepository(root)
    orchestrator = RunOrchestrator(repository, checkpoint_interval_ticks=5)
    request = RunRequestV2(
        topology_id="sioux_falls_tntp_v1",
        physical_profile_id="SiouxFallsPhysicalProfile_UC_Default_v1",
        demand_source_id="sioux_falls_canonical_od_v1",
        requested_packet_count=100,
        tick_policy_id="sioux_profile_default_v1",
        runtime_limit_seconds=60,
        tick_limit=600,
        run_label="Bounded Sioux Falls · 100 packets",
        note="Complete V2 acceptance artifact over the non-geographic TNTP topology diagram.",
    )
    created = orchestrator.create_run(request, _fixture_run_id=SIOUX_FALLS_BOUNDED_RUN_ID)
    final = orchestrator.wait(created.run_id, 120)
    if final.status != RunLifecycleState.COMPLETE or final.validation_status != "passed":
        raise RuntimeError(f"bounded Sioux Falls fixture failed: {final.status} {final.stop_reason}")
    return root / created.run_id
