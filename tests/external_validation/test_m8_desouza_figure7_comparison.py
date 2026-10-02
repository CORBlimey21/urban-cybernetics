# SPDX-License-Identifier: MPL-2.0
"""Integrity and metric regressions for the Figure 7(a) DT1 comparison."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/compare_desouza_figure7a_dt1.py"
EXPECTED_REFERENCES = {
    "Gu": ("852e02f91f4c1e5b98dc1bd8958f64a3efafcd5eef71f0ed546d2a790a6c2124", 220),
    "F1": ("f1decc34b3baeaf24fc64d8f46fee8eea05dc9a02d563aec78e9c1e1cd81c3d6", 165),
    "F2": ("8c40ab91eb62c5ca44c4f5e5a7e5c746beb9fd974b1427551bfc7a06582144cd", 113),
}


def _module():
    spec = importlib.util.spec_from_file_location("compare_desouza_figure7a_dt1", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_raw_digitised_references_are_preserved_exactly() -> None:
    module = _module()
    for name, path in module.DEFAULT_REFERENCES.items():
        expected_sha, expected_points = EXPECTED_REFERENCES[name]
        before = path.read_bytes()
        _, _, profile = module._load_reference(path)
        after = path.read_bytes()
        assert before == after
        assert hashlib.sha256(before).hexdigest() == expected_sha
        assert profile["point_count"] == expected_points
        assert profile["raw_point_order_preserved"] is True
        assert profile["input_duplicate_time_count"] == 0


def test_digitisation_closure_is_profiled_before_uc_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_render_plots", lambda *args: None)
    summary = module.compare(module.DEFAULT_REFERENCES, module.DEFAULT_UC_RESULT, tmp_path)
    closure = summary["digitisation_closure"]

    assert closure["shared_support_seconds"] == [9, 119]
    assert closure["sample_count"] == 111
    assert closure["mean_absolute_residual_packets"] == pytest.approx(0.4955539638860613)
    assert closure["rmse_residual_packets"] == pytest.approx(0.6536775795633433)
    assert closure["maximum_absolute_residual_packets"] == pytest.approx(1.8200137836127168)
    assert closure["signed_bias_packets"] == pytest.approx(-0.10994344591689521)
    assert closure["endpoint_residual_packets"] == pytest.approx(-0.3971586542569767)


def test_figure7a_series_metrics_and_uc_gates_are_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_render_plots", lambda *args: None)
    summary = module.compare(module.DEFAULT_REFERENCES, module.DEFAULT_UC_RESULT, tmp_path)
    expected = {
        "Gu": (2.6229893086031133, 46, 0.8439114553813438, 1.0807060357341862),
        "F1": (1.7953738775111248, 62, 0.7085398361559748, 0.8528273124755149),
        "F2": (1.0954605974359053, 41, 0.36818266090985996, 0.4952649045001793),
    }
    for name, (maximum, time, mae, rmse) in expected.items():
        series = summary["series"][name]
        assert series["maximum_absolute_difference_packets"] == pytest.approx(maximum)
        assert series["maximum_absolute_difference_time_seconds"] == time
        assert series["mean_absolute_difference_packets"] == pytest.approx(mae)
        assert series["rmse_packets"] == pytest.approx(rmse)

    gates = summary["uc_validation_gates"]
    assert gates["cumulative_closure_exact_every_tick"] is True
    assert gates["cumulative_closure_max_absolute_residual_packets"] == 0.0
    assert gates["final_route_split"] == [50.0, 16.0]
    assert summary["provenance"]["loading_engine_imported_or_executed"] is False
