"""Preserved-reference comparison for de Souza Figure 9 merge cases."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from bisect import bisect_right
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def compare_figure9_case(
    *,
    case_id: str,
    panel_id: str,
    evidence_path: Path,
    reference_paths: dict[str, Path],
    summary_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Compare G1/G2 only on each digitised trace's actual support."""

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    uc = {
        "G1": evidence["cumulative_outflow_l1"],
        "G2": evidence["cumulative_outflow_l2"],
    }
    references: dict[str, tuple[list[float], list[float]]] = {}
    integrity: dict[str, object] = {}
    comparisons: dict[str, list[dict[str, float]]] = {}
    metrics: dict[str, object] = {}
    audit: dict[str, object] = {}
    for series_id, path in reference_paths.items():
        times, values, profile = _load_reference(path)
        references[series_id] = (times, values)
        integrity[series_id] = profile
        start = math.ceil(times[0])
        end = math.floor(times[-1])
        rows = []
        for tick in range(start, end + 1):
            reference = _interpolate(times, values, tick)
            observed = uc[series_id][tick]
            difference = observed - reference
            rows.append({
                "time_seconds": float(tick),
                "uc_observed_vehicles": observed,
                "published_interpolated_reference_vehicles": reference,
                "difference_vehicles": difference,
                "absolute_difference_vehicles": abs(difference),
            })
        comparisons[series_id] = rows
        metrics[series_id] = {
            "comparison_support_seconds": [start, end],
            **_stats(rows),
            "regions": {
                "before_t40": _region(rows, start, min(39, end)),
                "after_t40": _region(rows, max(40, start), end),
                "early_after_t40": _region(rows, max(40, start), min(60, end)),
                "late_after_t40": _region(rows, max(61, start), end),
            },
        }
        audit[series_id] = {
            "first_absolute_difference_over_0_5": _audit_point(
                rows, times, values, evidence, series_id, 0.5
            ),
            "first_absolute_difference_over_2": _audit_point(
                rows, times, values, evidence, series_id, 2.0
            ),
            "maximum_absolute_difference": _audit_maximum(
                rows, times, values, evidence, series_id
            ),
            "reference_segment_slope_above_0_5_veh_per_second_count": sum(
                (right_value - left_value) / (right_time - left_time) > 0.5
                for left_time, right_time, left_value, right_value in zip(
                    times, times[1:], values, values[1:]
                )
                if right_time > left_time
            ),
            "reference_decreasing_segment_count": sum(
                right < left for left, right in zip(values, values[1:])
            ),
        }
    summary = {
        "schema_version": "uc.validation.published-comparison.v1",
        "comparison_id": f"desouza-figure9{panel_id}-comparison-v1",
        "case_id": case_id,
        "reference_classification": "published digitised figure data; not ground truth",
        "interpolation": {
            "method": "piecewise linear reference interpolation onto exact integer-second UC ticks",
            "uc_interpolated": False,
            "extrapolation": False,
            "each_series_compared_only_on_actual_reference_support": True,
        },
        "source_integrity": integrity,
        "series": metrics,
        "read_only_first_divergence_audit": {
            "trigger": "material differences above 2 vehicles observed",
            "series": audit,
            "kernel_mutated": False,
            "parameters_or_references_tuned": False,
        },
        "derived_downstream_inflow": "F3(t)=G1(t)+G2(t)",
        "uc_validation_gates": {
            key: evidence[key]
            for key in evidence
            if key.endswith("_check")
        },
        "uc_endpoints": {
            "G1": uc["G1"][-1],
            "G2": uc["G2"][-1],
            "F3": evidence["cumulative_inflow_l3"][-1],
            "maximum_queue_l1": max(evidence["eligible_queue_l1"]),
            "maximum_queue_l2": max(evidence["eligible_queue_l2"]),
            "final_queue_l1": evidence["eligible_queue_l1"][-1],
            "final_queue_l2": evidence["eligible_queue_l2"][-1],
        },
        "provenance": {
            "uc_evidence_path": _repo_path(evidence_path),
            "uc_evidence_sha256": _sha256(evidence_path),
            "loading_engine_imported_or_executed_by_comparator": False,
            "reference_files_modified": False,
        },
    }
    if "paper_priority_ambiguity_resolution" in evidence:
        summary["paper_priority_ambiguity_resolution"] = evidence[
            "paper_priority_ambiguity_resolution"
        ]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    for series_id, rows in comparisons.items():
        _write_csv(output_dir / f"{series_id}_comparison.csv", rows)
    _render_plots(output_dir, panel_id, references, uc, comparisons)
    return summary


def _load_reference(path: Path) -> tuple[list[float], list[float], dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames or []
    if len(fields) != 2 or fields[0] != "time_s":
        raise ValueError(f"unexpected reference schema: {fields}")
    raw_times = [float(row[fields[0]]) for row in rows]
    raw_values = [float(row[fields[1]]) for row in rows]
    ordered = sorted(enumerate(zip(raw_times, raw_values)), key=lambda item: item[1][0])
    times = [point[0] for _, point in ordered]
    values = [point[1] for _, point in ordered]
    return times, values, {
        "path": _repo_path(path),
        "sha256": _sha256(path),
        "point_count": len(rows),
        "support_seconds": [times[0], times[-1]],
        "raw_point_order_preserved": True,
        "input_nonincreasing_adjacent_pair_count": sum(
            right <= left for left, right in zip(raw_times, raw_times[1:])
        ),
        "input_duplicate_time_count": len(raw_times) - len(set(raw_times)),
        "stable_sort_retained_input_order_for_equal_times": True,
        "sorted_value_decrease_count": sum(
            right < left for left, right in zip(values, values[1:])
        ),
        "analysis_time_normalization": (
            "stable ascending time sort only; no smoothing, averaging, fitting, shifting, "
            "monotonicisation, point removal, or synthetic origin"
        ),
    }


def _interpolate(times: list[float], values: list[float], tick: int) -> float:
    right = bisect_right(times, tick)
    if right == 0 or right == len(times):
        return values[0] if right == 0 else values[-1]
    left = right - 1
    span = times[right] - times[left]
    if span == 0:
        return values[right]
    weight = (tick - times[left]) / span
    return values[left] + weight * (values[right] - values[left])


def _stats(rows: list[dict[str, float]]) -> dict[str, float | int | None]:
    differences = [row["difference_vehicles"] for row in rows]
    times = [int(row["time_seconds"]) for row in rows]
    absolute = [abs(value) for value in differences]
    maximum = max(absolute)
    result: dict[str, float | int | None] = {
        "sample_count": len(rows),
        "maximum_absolute_difference_vehicles": maximum,
        "maximum_absolute_difference_time_seconds": times[absolute.index(maximum)],
        "mean_absolute_difference_vehicles": sum(absolute) / len(absolute),
        "rmse_vehicles": math.sqrt(sum(value * value for value in differences) / len(differences)),
        "final_comparable_signed_difference_vehicles": differences[-1],
        "signed_difference_slope_vehicles_per_second": _least_squares_slope(times, differences),
        "mean_signed_difference_vehicles": sum(differences) / len(differences),
    }
    for label, threshold in (("0_5", 0.5), ("1", 1.0), ("2", 2.0)):
        result[f"first_absolute_difference_exceeds_{label}_vehicles_seconds"] = next(
            (tick for tick, value in zip(times, absolute) if value > threshold), None
        )
    return result


def _region(rows: list[dict[str, float]], start: int, end: int) -> dict[str, object]:
    selected = [row for row in rows if start <= row["time_seconds"] <= end]
    if not selected:
        return {"start_seconds": start, "end_seconds": end, "sample_count": 0}
    return {"start_seconds": start, "end_seconds": end, **_stats(selected)}


def _least_squares_slope(times: list[int], differences: list[float]) -> float:
    x_mean = sum(times) / len(times)
    y_mean = sum(differences) / len(differences)
    denominator = sum((tick - x_mean) ** 2 for tick in times)
    return 0.0 if denominator == 0 else sum(
        (tick - x_mean) * (value - y_mean)
        for tick, value in zip(times, differences)
    ) / denominator


def _audit_point(
    rows: list[dict[str, float]],
    reference_times: list[float],
    reference_values: list[float],
    evidence: dict[str, object],
    series_id: str,
    threshold: float,
) -> dict[str, object] | None:
    row = next(
        (item for item in rows if abs(item["difference_vehicles"]) > threshold),
        None,
    )
    return None if row is None else _audit_row(
        row, reference_times, reference_values, evidence, series_id
    )


def _audit_maximum(
    rows: list[dict[str, float]],
    reference_times: list[float],
    reference_values: list[float],
    evidence: dict[str, object],
    series_id: str,
) -> dict[str, object]:
    row = max(rows, key=lambda item: abs(item["difference_vehicles"]))
    return _audit_row(row, reference_times, reference_values, evidence, series_id)


def _audit_row(
    row: dict[str, float],
    reference_times: list[float],
    reference_values: list[float],
    evidence: dict[str, object],
    series_id: str,
) -> dict[str, object]:
    tick = int(row["time_seconds"])
    right = min(max(1, bisect_right(reference_times, tick)), len(reference_times) - 1)
    left = right - 1
    span = reference_times[right] - reference_times[left]
    slope = (
        (reference_values[right] - reference_values[left]) / span
        if span else None
    )
    queue_key = "eligible_queue_l1" if series_id == "G1" else "eligible_queue_l2"
    cumulative_key = "cumulative_outflow_l1" if series_id == "G1" else "cumulative_outflow_l2"
    transfer_sources = dict(evidence["transfer_source_by_tick"])
    return {
        **row,
        "reference_bracketing_points": [
            [reference_times[left], reference_values[left]],
            [reference_times[right], reference_values[right]],
        ],
        "reference_local_segment_slope_vehicles_per_second": slope,
        "uc_previous_tick_value": (
            evidence[cumulative_key][tick - 1]
            if tick > 0 else None
        ),
        "uc_eligible_queue_at_tick": evidence[queue_key][tick],
        "uc_transfer_sources_at_tick": transfer_sources.get(tick, ()),
    }


def _write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _render_plots(
    output: Path,
    panel_id: str,
    references: dict[str, tuple[list[float], list[float]]],
    uc: dict[str, list[int]],
    comparisons: dict[str, list[dict[str, float]]],
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    colors = {"G1": "#7A3E9D", "G2": "#0072B2"}
    font = ImageFont.load_default(size=24)
    title_font = ImageFont.load_default(size=34)

    def canvas(title: str, ylabel: str, ymin: float, ymax: float):
        image = Image.new("RGB", (1890, 1080), "#FAFBFC")
        draw = ImageDraw.Draw(image)
        left, top, right, bottom = 155, 145, 1820, 960
        draw.text((left, 35), title, fill="#263238", font=title_font)
        draw.text((left, 90), ylabel, fill="#455A64", font=font)
        for tick in range(0, 121, 20):
            x = left + (right - left) * tick / 120
            draw.line((x, top, x, bottom), fill="#D9DEE5", width=2)
            draw.text((x - 12, bottom + 15), str(tick), fill="#455A64", font=font)
        y_step = 5 if ymax - ymin <= 30 else 10
        value = math.ceil(ymin / y_step) * y_step
        while value <= ymax:
            y = bottom - (bottom - top) * (value - ymin) / (ymax - ymin)
            draw.line((left, y, right, y), fill="#D9DEE5", width=2)
            draw.text((left - 60, y - 12), f"{value:g}", fill="#455A64", font=font)
            value += y_step
        draw.line((left, top, left, bottom), fill="#263238", width=3)
        draw.line((left, bottom, right, bottom), fill="#263238", width=3)
        return image, draw, (left, top, right, bottom)

    def xy(bounds, tick, value, ymin, ymax):
        left, top, right, bottom = bounds
        return (
            left + (right - left) * tick / 120,
            bottom - (bottom - top) * (value - ymin) / (ymax - ymin),
        )

    image, draw, bounds = canvas(
        f"de Souza Figure 9({panel_id}): digitised references and frozen UC",
        "Cumulative outflow (vehicles); thick reference, thin UC", 0, 40,
    )
    for series_id in ("G1", "G2"):
        times, values = references[series_id]
        draw.line([xy(bounds, t, v, 0, 40) for t, v in zip(times, values)],
                  fill=colors[series_id], width=5)
        step_points = []
        for tick, value in enumerate(uc[series_id]):
            point = xy(bounds, tick, value, 0, 40)
            if step_points:
                step_points.append((point[0], step_points[-1][1]))
            step_points.append(point)
        draw.line(step_points, fill=colors[series_id], width=2)
    change_x = xy(bounds, 40, 0, 0, 40)[0]
    draw.line((change_x, bounds[1], change_x, bounds[3]), fill="#555555", width=3)
    draw.text((bounds[0] + 25, bounds[1] + 20), "purple G1; blue G2; vertical line t=40", fill="#263238", font=font)
    image.save(output / "overlay.png", dpi=(180, 180))

    differences = [row["difference_vehicles"] for rows in comparisons.values() for row in rows]
    ymin = min(-2.5, math.floor(min(differences) - 0.5))
    ymax = max(2.5, math.ceil(max(differences) + 0.5))
    image, draw, bounds = canvas(
        f"Figure 9({panel_id}): UC minus digitised reference on actual supports",
        "Signed difference (vehicles)", ymin, ymax,
    )
    for threshold in (-2, -1, -0.5, 0, 0.5, 1, 2):
        y = xy(bounds, 0, threshold, ymin, ymax)[1]
        draw.line((bounds[0], y, bounds[2], y),
                  fill="#263238" if threshold == 0 else "#969DA6",
                  width=3 if threshold == 0 else 2)
    for series_id, rows in comparisons.items():
        draw.line([
            xy(bounds, row["time_seconds"], row["difference_vehicles"], ymin, ymax)
            for row in rows
        ], fill=colors[series_id], width=4)
    change_x = xy(bounds, 40, 0, ymin, ymax)[0]
    draw.line((change_x, bounds[1], change_x, bounds[3]), fill="#555555", width=3)
    image.save(output / "difference.png", dpi=(180, 180))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_path(path: Path) -> str:
    return str(path.relative_to(ROOT))
