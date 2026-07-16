"""Compare preserved de Souza Figure 7(a) digitisation with frozen UC evidence.

The script consumes persisted evidence only. It neither imports nor executes
the loading engine, and it never rewrites the preserved reference CSVs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from bisect import bisect_right
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/validation"
DEFAULT_REFERENCES = {
    "Gu": DATA / "desouza_figure7a_dt1_Gu_digitised_v1.csv",
    "F1": DATA / "desouza_figure7a_dt1_F1_digitised_v1.csv",
    "F2": DATA / "desouza_figure7a_dt1_F2_digitised_v1.csv",
}
DEFAULT_UC_RESULT = (
    ROOT / "fixtures/visualisation/validation/runs/"
    "m8-pub-dsouza-fig7-dt1-baseline-v1/result.json"
)
DEFAULT_OUTPUT = ROOT / "outputs/validation/m8_desouza_figure7a_dt1_comparison_v1"
UC_SERIES = {
    "Gu": "upstream_cumulative_outflow",
    "F1": "downstream_1_cumulative_inflow",
    "F2": "downstream_2_cumulative_inflow",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_reference(path: Path) -> tuple[list[float], list[float], dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames or []
    if len(fields) != 2 or fields[0] != "time_s":
        raise ValueError(f"unexpected reference schema in {path}: {fields}")
    raw_times = [float(row[fields[0]]) for row in rows]
    raw_values = [float(row[fields[1]]) for row in rows]
    if len(raw_times) < 2:
        raise ValueError(f"reference has fewer than two points: {path}")
    indexed = list(enumerate(zip(raw_times, raw_values)))
    ordered = sorted(indexed, key=lambda item: item[1][0])
    times = [point[0] for _, point in ordered]
    values = [point[1] for _, point in ordered]
    return times, values, {
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha256(path),
        "point_count": len(rows),
        "time_column": fields[0],
        "value_column": fields[1],
        "raw_point_order_preserved": True,
        "input_nonincreasing_adjacent_pair_count": sum(
            right <= left for left, right in zip(raw_times, raw_times[1:])
        ),
        "input_duplicate_time_count": len(raw_times) - len(set(raw_times)),
        "stable_sort_retained_input_order_for_equal_times": True,
        "analysis_time_normalization": (
            "stable ascending time sort only; no averaging, smoothing, monotonicisation, "
            "fitting, shifting, point removal, or synthetic origin"
        ),
        "support_seconds": [times[0], times[-1]],
        "sorted_value_decrease_count": sum(
            right < left for left, right in zip(values, values[1:])
        ),
    }


def _load_uc(path: Path) -> tuple[dict[str, tuple[list[int], list[float]]], dict[str, object]]:
    result = json.loads(path.read_text(encoding="utf-8"))
    available = {series["series_id"]: series for series in result["observed_series"]}
    loaded = {}
    for name, series_id in UC_SERIES.items():
        series = available[series_id]
        loaded[name] = (list(series["ticks"]), list(series["values"]))
    return loaded, result


def _interpolate(times: list[float], values: list[float], time: float) -> float:
    if not times[0] <= time <= times[-1]:
        raise ValueError("comparison time lies outside reference support")
    right = bisect_right(times, time)
    if right == 0:
        return values[0]
    if right == len(times):
        return values[-1]
    left = right - 1
    span = times[right] - times[left]
    if span == 0:
        return values[right]
    weight = (time - times[left]) / span
    return values[left] + weight * (values[right] - values[left])


def _least_squares_slope(xs: list[float], ys: list[float]) -> float:
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    return 0.0 if denominator == 0 else sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)
    ) / denominator


def _stats(
    differences: list[float], times: list[int], *, include_thresholds: bool = True,
) -> dict[str, float | int | None]:
    absolute = [abs(value) for value in differences]
    maximum = max(absolute)
    result: dict[str, float | int | None] = {
        "sample_count": len(differences),
        "maximum_absolute_difference_packets": maximum,
        "maximum_absolute_difference_time_seconds": times[absolute.index(maximum)],
        "mean_absolute_difference_packets": sum(absolute) / len(absolute),
        "rmse_packets": math.sqrt(
            sum(value * value for value in differences) / len(differences)
        ),
        "mean_signed_difference_packets": sum(differences) / len(differences),
        "start_signed_difference_packets": differences[0],
        "final_signed_difference_packets": differences[-1],
        "signed_difference_slope_packets_per_second": _least_squares_slope(
            [float(time) for time in times], differences
        ),
    }
    if include_thresholds:
        for label, threshold in (("0_5", 0.5), ("1", 1.0), ("2", 2.0)):
            result[f"first_absolute_difference_exceeds_{label}_packets_seconds"] = next(
                (time for time, value in zip(times, absolute) if value > threshold), None
            )
    return result


def _region(rows: list[dict[str, float]], start: int, end: int) -> dict[str, object]:
    selected = [row for row in rows if start <= row["time_seconds"] <= end]
    return {
        "start_seconds": start,
        "end_seconds": end,
        **_stats(
            [row["difference_packets"] for row in selected],
            [int(row["time_seconds"]) for row in selected],
            include_thresholds=False,
        ),
    }


def _write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_plots(
    output: Path,
    references: dict[str, tuple[list[float], list[float]]],
    uc: dict[str, tuple[list[int], list[float]]],
    comparison_rows: dict[str, list[dict[str, float]]],
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1890, 1080
    left, top, right, bottom = 155, 145, width - 70, height - 120
    background, grid, ink = "#FAFBFC", "#D9DEE5", "#263238"
    colors = {"Gu": "#7A3E9D", "F1": "#0072B2", "F2": "#D55E00"}
    regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    font = ImageFont.truetype(regular, 25)
    title_font = ImageFont.truetype(bold, 34)

    def canvas(title: str, ylabel: str, ymin: float, ymax: float):
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        draw.text((left, 35), title, fill=ink, font=title_font)
        draw.text((left, 93), ylabel, fill=ink, font=font)
        for tick in range(0, 121, 20):
            x = left + (right - left) * tick / 120
            draw.line((x, top, x, bottom), fill=grid, width=2)
            draw.text((x - 12, bottom + 16), str(tick), fill=ink, font=font)
        step = 10 if ymax - ymin > 30 else 2
        value = math.ceil(ymin / step) * step
        while value <= ymax:
            y = bottom - (bottom - top) * (value - ymin) / (ymax - ymin)
            draw.line((left, y, right, y), fill=grid, width=2)
            draw.text((left - 55, y - 12), f"{value:g}", fill=ink, font=font)
            value += step
        draw.line((left, top, left, bottom), fill=ink, width=3)
        draw.line((left, bottom, right, bottom), fill=ink, width=3)
        return image, draw

    def xy(time: float, value: float, ymin: float, ymax: float):
        return (
            left + (right - left) * time / 120,
            bottom - (bottom - top) * (value - ymin) / (ymax - ymin),
        )

    image, draw = canvas(
        "de Souza Figure 7(a): digitised references and frozen UC DT=1",
        "Cumulative vehicles", 0, 70,
    )
    for name in ("Gu", "F1", "F2"):
        ref_times, ref_values = references[name]
        draw.line(
            [xy(t, v, 0, 70) for t, v in zip(ref_times, ref_values)],
            fill=colors[name], width=4, joint="curve",
        )
        uc_times, uc_values = uc[name]
        step_points = []
        for index, (time, value) in enumerate(zip(uc_times, uc_values)):
            point = xy(time, value, 0, 70)
            if index:
                step_points.append((point[0], step_points[-1][1]))
            step_points.append(point)
        draw.line(step_points, fill=colors[name], width=2)
    draw.line((xy(50, 0, 0, 70)[0], top, xy(50, 0, 0, 70)[0], bottom), fill="#555555", width=3)
    draw.text((left + 25, top + 20), "thick=reference; thin=UC", fill=ink, font=font)
    draw.text((left + 25, top + 55), "purple Gu; blue F1; orange F2", fill=ink, font=font)
    image.save(output / "overlay.png", dpi=(180, 180))

    all_differences = [
        row["difference_packets"]
        for rows in comparison_rows.values() for row in rows
    ]
    ymin = math.floor(min(all_differences) - 0.5)
    ymax = math.ceil(max(all_differences) + 0.5)
    image, draw = canvas(
        "UC minus digitised reference on each actual support",
        "Signed difference (vehicles)", ymin, ymax,
    )
    for threshold in (-2, -1, -0.5, 0, 0.5, 1, 2):
        y = xy(0, threshold, ymin, ymax)[1]
        draw.line((left, y, right, y), fill="#333333" if threshold == 0 else "#969DA6", width=3 if threshold == 0 else 2)
    for name, rows in comparison_rows.items():
        draw.line(
            [xy(row["time_seconds"], row["difference_packets"], ymin, ymax) for row in rows],
            fill=colors[name], width=4, joint="curve",
        )
    draw.line((xy(50, 0, ymin, ymax)[0], top, xy(50, 0, ymin, ymax)[0], bottom), fill="#555555", width=3)
    image.save(output / "difference.png", dpi=(180, 180))


def compare(reference_paths: dict[str, Path], uc_path: Path, output: Path) -> dict[str, object]:
    references: dict[str, tuple[list[float], list[float]]] = {}
    integrity: dict[str, object] = {}
    for name, path in reference_paths.items():
        times, values, profile = _load_reference(path)
        references[name] = (times, values)
        integrity[name] = profile
    uc, uc_result = _load_uc(uc_path)

    shared_start = math.ceil(max(values[0][0] for values in references.values()))
    shared_end = math.floor(min(values[0][-1] for values in references.values()))
    closure_times = list(range(shared_start, shared_end + 1))
    closure_rows = []
    for time in closure_times:
        gu = _interpolate(*references["Gu"], time)
        f1 = _interpolate(*references["F1"], time)
        f2 = _interpolate(*references["F2"], time)
        closure_rows.append({
            "time_seconds": float(time), "Gu_reference_packets": gu,
            "F1_reference_packets": f1, "F2_reference_packets": f2,
            "closure_residual_packets": gu - f1 - f2,
        })
    closure_residuals = [row["closure_residual_packets"] for row in closure_rows]
    closure_absolute = [abs(value) for value in closure_residuals]
    closure = {
        "shared_support_seconds": [shared_start, shared_end],
        "sample_count": len(closure_rows),
        "mean_absolute_residual_packets": sum(closure_absolute) / len(closure_absolute),
        "rmse_residual_packets": math.sqrt(
            sum(value * value for value in closure_residuals) / len(closure_residuals)
        ),
        "maximum_absolute_residual_packets": max(closure_absolute),
        "maximum_absolute_residual_time_seconds": closure_times[
            closure_absolute.index(max(closure_absolute))
        ],
        "signed_bias_packets": sum(closure_residuals) / len(closure_residuals),
        "endpoint_residual_packets": closure_residuals[-1],
    }

    comparison_rows: dict[str, list[dict[str, float]]] = {}
    series_results: dict[str, object] = {}
    for name, (reference_times, reference_values) in references.items():
        start = math.ceil(reference_times[0])
        end = math.floor(reference_times[-1])
        times = list(range(start, end + 1))
        uc_by_time = dict(zip(*uc[name]))
        rows = []
        for time in times:
            reference = _interpolate(reference_times, reference_values, time)
            observed = uc_by_time[time]
            difference = observed - reference
            rows.append({
                "time_seconds": float(time), "uc_observed_packets": observed,
                "published_interpolated_reference_packets": reference,
                "difference_packets": difference,
                "absolute_difference_packets": abs(difference),
            })
        comparison_rows[name] = rows
        series_results[name] = {
            "comparison_support_seconds": [start, end],
            **_stats([row["difference_packets"] for row in rows], times),
            "regions": {
                "before_demand_change": _region(rows, start, 49),
                "transition_window": _region(rows, 50, min(60, end)),
                "after_transition": _region(rows, 61, end),
                "after_demand_change_combined": _region(rows, 50, end),
            },
        }

    uc_gu = uc["Gu"][1]
    uc_f1 = uc["F1"][1]
    uc_f2 = uc["F2"][1]
    summary = {
        "schema_version": "uc.validation.published-comparison.v1",
        "comparison_id": "m8-desouza-figure7a-dt1-comparison-v1",
        "case_id": uc_result["case_id"],
        "uc_result_id": uc_result["result_id"],
        "reference_classification": "published digitised figure data; not ground truth",
        "interpolation": {
            "method": "piecewise linear reference interpolation onto exact integer-second UC ticks",
            "uc_interpolated": False, "extrapolation": False,
            "each_series_compared_only_on_actual_reference_support": True,
        },
        "source_integrity": integrity,
        "digitisation_closure": closure,
        "series": series_results,
        "uc_validation_gates": {
            "cumulative_closure_exact_every_tick": all(
                gu == f1 + f2 for gu, f1, f2 in zip(uc_gu, uc_f1, uc_f2)
            ),
            "cumulative_closure_max_absolute_residual_packets": max(
                abs(gu - f1 - f2) for gu, f1, f2 in zip(uc_gu, uc_f1, uc_f2)
            ),
            "final_upstream_outflow_packets": uc_gu[-1],
            "final_downstream_1_inflow_packets": uc_f1[-1],
            "final_downstream_2_inflow_packets": uc_f2[-1],
            "final_route_split": [uc_f1[-1], uc_f2[-1]],
        },
        "provenance": {
            "uc_result_path": str(uc_path.relative_to(ROOT)),
            "uc_result_sha256": _sha256(uc_path),
            "loading_engine_imported_or_executed": False,
            "reference_files_modified": False,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "digitisation_closure.csv", closure_rows)
    for name, rows in comparison_rows.items():
        _write_csv(output / f"{name}_comparison_series.csv", rows)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    _render_plots(output, references, uc, comparison_rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gu-reference", type=Path, default=DEFAULT_REFERENCES["Gu"])
    parser.add_argument("--f1-reference", type=Path, default=DEFAULT_REFERENCES["F1"])
    parser.add_argument("--f2-reference", type=Path, default=DEFAULT_REFERENCES["F2"])
    parser.add_argument("--uc-result", type=Path, default=DEFAULT_UC_RESULT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = compare(
        {"Gu": args.gu_reference, "F1": args.f1_reference, "F2": args.f2_reference},
        args.uc_result, args.output,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
