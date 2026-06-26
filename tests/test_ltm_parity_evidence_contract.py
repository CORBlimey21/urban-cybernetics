"""Academic LTM parity claim and evidence-contract tests."""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    DEFAULT_LOADING_PROFILE_ID,
    LEGACY_LOADING_PROFILE_ID,
    loading_profile_config,
)
from urban_cybernetics.provenance import (
    ParityRunEvidence,
    RunArtifactIndex,
    RunMetadata,
    RunRecorder,
    RunSummary,
)
from urban_cybernetics.validation import (
    PARITY_SPEC_VERSION,
    ParityEvidenceContract,
    parity_profile_status,
)


class LTMParityEvidenceContractTest(unittest.TestCase):
    def test_loading_profile_config_records_kernel_profile_for_provenance(self) -> None:
        self.assertEqual(DEFAULT_LOADING_PROFILE_ID, LEGACY_LOADING_PROFILE_ID)
        self.assertEqual(
            loading_profile_config(),
            {
                "model_kernel_profile_id": LEGACY_LOADING_PROFILE_ID,
                "model_kernel_profile_status": "legacy_compatible",
            },
        )
        self.assertEqual(
            loading_profile_config(ACADEMIC_LTM_PARITY_PROFILE_ID),
            {
                "model_kernel_profile_id": ACADEMIC_LTM_PARITY_PROFILE_ID,
                "model_kernel_profile_status": "parity_eligible",
            },
        )
        with self.assertRaises(ValueError):
            loading_profile_config("unknown")

    def test_parity_profile_status_classifies_only_supported_profiles(self) -> None:
        self.assertEqual(
            parity_profile_status(LEGACY_LOADING_PROFILE_ID),
            "legacy_compatible",
        )
        self.assertEqual(
            parity_profile_status(ACADEMIC_LTM_PARITY_PROFILE_ID),
            "parity_eligible",
        )
        with self.assertRaises(ValueError):
            parity_profile_status("adhoc")

    def test_evidence_contract_is_frozen_and_validates_claim_tiers(self) -> None:
        contract = ParityEvidenceContract(contract_id="academic-ltm-parity-v1")

        self.assertEqual(contract.spec_version, PARITY_SPEC_VERSION)
        self.assertIn("t3_packet_multi_commodity_parity", contract.accepted_claim_tiers)
        with self.assertRaises(FrozenInstanceError):
            contract.contract_id = "changed"
        with self.assertRaises(ValueError):
            ParityEvidenceContract(
                contract_id="bad",
                accepted_claim_tiers=("unsupported",),
            )

    def test_parity_run_evidence_records_failure_semantics(self) -> None:
        for reason in (
            "partial_run",
            "interrupted_run",
            "timed_out",
            "inconsistent_state",
            "unsupported_profile",
            "validation_failed",
        ):
            with self.subTest(reason=reason):
                evidence = ParityRunEvidence(
                    run_id="run-1",
                    claim_tier="none",
                    model_profile_id=LEGACY_LOADING_PROFILE_ID,
                    evidence_status="not_parity_evidence",
                    failure_reason=reason,
                )
                self.assertEqual(evidence.failure_reason, reason)

        with self.assertRaises(ValueError):
            ParityRunEvidence(
                run_id="run-1",
                claim_tier="t0_architecture_compatible",
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                evidence_status="failed",
            )
        with self.assertRaises(ValueError):
            ParityRunEvidence(
                run_id="run-1",
                claim_tier="none",
                model_profile_id=LEGACY_LOADING_PROFILE_ID,
                evidence_status="not_assessed",
                failure_reason="partial_run",
            )

    def test_passed_parity_evidence_requires_parity_profile_and_claim_tier(self) -> None:
        passed = ParityRunEvidence(
            run_id="run-1",
            claim_tier="t0_architecture_compatible",
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
            evidence_status="passed",
        )
        self.assertEqual(passed.failure_reason, "none")

        with self.assertRaises(ValueError):
            ParityRunEvidence(
                run_id="run-1",
                claim_tier="t0_architecture_compatible",
                model_profile_id=LEGACY_LOADING_PROFILE_ID,
                evidence_status="passed",
            )
        with self.assertRaises(ValueError):
            ParityRunEvidence(
                run_id="run-1",
                claim_tier="none",
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                evidence_status="passed",
            )
        with self.assertRaises(ValueError):
            ParityRunEvidence(
                run_id="run-1",
                claim_tier="t0_architecture_compatible",
                model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
                evidence_status="passed",
                failure_reason="validation_failed",
            )

    def test_run_summary_can_carry_optional_parity_evidence(self) -> None:
        metadata = RunMetadata(run_id="run-1", scenario_name="parity label")
        evidence = ParityRunEvidence(
            run_id="run-1",
            claim_tier="none",
            model_profile_id=LEGACY_LOADING_PROFILE_ID,
            evidence_status="not_assessed",
        )

        summary = RunSummary(
            metadata=metadata,
            config_snapshot=None,
            artifact_index=RunArtifactIndex(run_id="run-1"),
            parity_evidence=evidence,
        )

        self.assertEqual(summary.parity_evidence, evidence)
        with self.assertRaises(ValueError):
            RunSummary(
                metadata=metadata,
                config_snapshot=None,
                artifact_index=RunArtifactIndex(run_id="run-1"),
                parity_evidence=ParityRunEvidence(
                    run_id="other-run",
                    claim_tier="none",
                    model_profile_id=LEGACY_LOADING_PROFILE_ID,
                    evidence_status="not_assessed",
                ),
            )

    def test_recorder_seals_parity_evidence_without_changing_existing_status(self) -> None:
        recorder = RunRecorder(
            RunMetadata(run_id="run-1", scenario_name="parity metadata")
        )
        recorder.record_config(
            {
                "scenario": "tiny",
                **loading_profile_config(LEGACY_LOADING_PROFILE_ID),
            }
        )
        evidence = ParityRunEvidence(
            run_id="run-1",
            claim_tier="none",
            model_profile_id=LEGACY_LOADING_PROFILE_ID,
            evidence_status="not_parity_evidence",
            failure_reason="unsupported_profile",
        )

        summary = recorder.seal(
            validation_status="passed",
            parity_evidence=evidence,
        )

        self.assertEqual(summary.validation_status, "passed")
        self.assertEqual(summary.parity_evidence, evidence)
        self.assertEqual(
            summary.config_snapshot.config["model_kernel_profile_id"],  # type: ignore[union-attr]
            LEGACY_LOADING_PROFILE_ID,
        )

    def test_validation_claim_shell_does_not_import_loading(self) -> None:
        validation_root = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "urban_cybernetics"
            / "validation"
        )
        imported_modules: set[str] = set()
        for source_path in validation_root.glob("*.py"):
            tree = ast.parse(source_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.add(node.module)

        self.assertNotIn("urban_cybernetics.loading", imported_modules)
        self.assertNotIn("urban_cybernetics.loading.engine", imported_modules)


if __name__ == "__main__":
    unittest.main()
