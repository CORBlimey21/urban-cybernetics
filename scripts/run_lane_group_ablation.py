#!/usr/bin/env python3
"""Generate the versioned Paper 1 lane-group ablation evidence artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from urban_cybernetics.core import (
    DemandDeclaration,
    JunctionSpec,
    Link,
    MovementSpec,
    Node,
)
from urban_cybernetics.experiments.lane_group_ablation import (
    AblationControl,
    run_lane_group_ablation,
)
from urban_cybernetics.loading.lane_group_extension import (
    ExplicitLaneGroup,
    LaneGroupProvenance,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "data/validation/paper1_lane_group_ablation_evidence_v1.json"
)
FREEZE_MANIFEST = ROOT / "data/validation/loading_kernel_freeze_manifest_v1.json"


def _link(link_id: str) -> Link:
    return Link(
        link_id,
        free_flow_ticks=1,
        declared_sending_capacity_per_tick=4,
        declared_receiving_capacity_per_tick=4,
        declared_storage_capacity_packets=20,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=100.0,
        backward_wave_speed_mps=5.0,
        capacity_veh_per_hour_per_lane=1200.0,
        tick_duration_seconds=1.0,
    )


def _group(group_id: str, downstream_id: str) -> ExplicitLaneGroup:
    return ExplicitLaneGroup(
        lane_group_id=group_id,
        node_id="N",
        incoming_link_id="U",
        allowed_movement_ids=(f"movement:U->{downstream_id}",),
        service_capacity_per_tick=1,
        provenance=LaneGroupProvenance(
            source="canonical-fixture",
            confidence=1.0,
            status="declared",
            compiler_version="manual-v1",
        ),
    )


def build_evidence() -> dict[str, object]:
    node = Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("L", "R"),
        junction_spec=JunctionSpec(
            node_id="N",
            incoming_link_ids=("U",),
            outgoing_link_ids=("L", "R"),
            movement_specs=(
                MovementSpec("U", "L"),
                MovementSpec("U", "R"),
            ),
        ),
    )
    result = run_lane_group_ablation(
        links={"U": _link("U"), "L": _link("L"), "R": _link("R")},
        nodes=(node,),
        lane_groups=(_group("left", "L"), _group("right", "R")),
        demands=(
            DemandDeclaration("left", 0, ("U", "L")),
            DemandDeclaration("right", 0, ("U", "R")),
        ),
        controls=(
            AblationControl(1, "receiving_open", "L", False),
            AblationControl(2, "receiving_open", "L", True),
        ),
        max_ticks=10,
    )
    runs = {run.representation_mode: run for run in result.runs}
    frozen_runtime = runs["shared_link_fifo"].runtime_seconds
    freeze_manifest = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))
    frozen_entries = [
        entry
        for category in freeze_manifest["artifacts"].values()
        for entry in category
    ]
    frozen_hashes_match = all(
        hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
        == entry["sha256"]
        for entry in frozen_entries
    )
    return {
        "evidence_version": "paper1-lane-group-extension-evidence-v1",
        "base_kernel_contract": {
            "freeze_version": "loading-kernel-v1.0.1",
            "freeze_manifest_path": str(FREEZE_MANIFEST.relative_to(ROOT)),
            "freeze_manifest_sha256": hashlib.sha256(
                FREEZE_MANIFEST.read_bytes()
            ).hexdigest(),
            "frozen_source_files_modified": False,
        },
        "baseline_equality_evidence": {
            "recorded_artifact_count": len(frozen_entries),
            "recorded_artifact_hashes_match": frozen_hashes_match,
            "verification_command": (
                ".venv/bin/python scripts/verify_loading_kernel_freeze.py"
            ),
            "protected_outputs": [
                "canonical event logs",
                "allocation traces",
                "benchmark RMSE values",
                "packet outcomes and completion counts",
                "terminal ticks",
                "conservation reports",
                "event/cache consistency",
                "cumulative-count consistency",
            ],
        },
        "fixture_path": (
            "fixtures/lane_groups/v1/canonical_lane_group_cases_v1.json"
        ),
        "fixture_gate": {
            "focused_test": "tests/test_lane_group_extension.py",
            "covered_cases": [
                "shared-single-group",
                "separated-groups",
                "partially-shared-alternative",
                "signal-interaction",
                "downstream-blockage",
                "conflict-coupling",
                "persistent-separate-group-queue-exit",
                "exact-determinism",
                "conservation-and-replay",
            ],
        },
        "ablation": result.as_dict(),
        "runtime_relative_to_shared_link_fifo": {
            mode: (
                run.runtime_seconds / frozen_runtime
                if frozen_runtime > 0.0
                else None
            )
            for mode, run in runs.items()
        },
        "safe_interpretation": (
            "Controlled mesoscopic queue-partition evidence only; not a "
            "microscopic lane-changing or lateral-position model."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_evidence()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
