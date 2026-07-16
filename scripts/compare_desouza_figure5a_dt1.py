"""Compare preserved Figure 5(a) digitisation with existing UC DT=1 evidence.

This script is an evidence consumer. It does not import or execute the loading
engine and does not modify the source validation fixture.
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
DEFAULT_REFERENCE = ROOT / "data/validation/desouza_figure5a_cumulative_inflow_digitised_v1.csv"
DEFAULT_UC_RESULT = ROOT / "fixtures/visualisation/validation/runs/m8-pub-dsouza-fig5-dt1-baseline-v1/result.json"
DEFAULT_OUTPUT = ROOT / "outputs/validation/m8_desouza_figure5a_dt1_comparison_v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_reference(
    path: Path, *, stable_time_sort: bool = False,
) -> tuple[list[float], list[float], str, dict[str, int | str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        value_columns = [name for name in (reader.fieldnames or ()) if name != "time_seconds"]
    if len(value_columns) != 1:
        raise ValueError("digitised reference must contain time_seconds and exactly one value column")
    value_column = value_columns[0]
    times = [float(row["time_seconds"]) for row in rows]
    values = [float(row[value_column]) for row in rows]
    if len(times) < 2:
        raise ValueError("digitised reference must contain at least two points")
    nonincreasing = sum(right <= left for left, right in zip(times, times[1:]))
    duplicate_count = len(times) - len(set(times))
    if stable_time_sort:
        ordered = sorted(zip(times, values), key=lambda point: point[0])
        times = [point[0] for point in ordered]
        values = [point[1] for point in ordered]
    elif nonincreasing:
        raise ValueError("digitised reference times must be strictly increasing unless stable time sort is declared")
    return times, values, value_column, {
        "input_nonincreasing_adjacent_pair_count": nonincreasing,
        "input_duplicate_time_count": duplicate_count,
        "time_normalization": (
            "stable ascending sort; duplicate-time values retain supplied order; no averaging or removal"
            if stable_time_sort else "none"
        ),
    }


def _load_uc(path: Path, series_id: str) -> tuple[list[int], list[float], dict[str, object]]:
    result = json.loads(path.read_text(encoding="utf-8"))
    matches = [
        series for series in result["observed_series"]
        if series["series_id"] == series_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {series_id} series")
    series = matches[0]
    return list(series["ticks"]), list(series["values"]), result


def _linear_interpolate(times: list[float], values: list[float], time: float) -> float:
    if not times[0] <= time <= times[-1]:
        raise ValueError("comparison time lies outside digitised reference support")
    right = bisect_right(times, time)
    if right == 0:
        return values[0]
    if right == len(times):
        return values[-1]
    left = right - 1
    weight = (time - times[left]) / (times[right] - times[left])
    return values[left] + weight * (values[right] - values[left])


def _summary(rows: list[dict[str, float]], start: int, end: int) -> dict[str, float | int]:
    selected = [row for row in rows if start <= row["time_seconds"] <= end]
    differences = [row["difference_packets"] for row in selected]
    absolute = [abs(value) for value in differences]
    return {
        "start_seconds": start,
        "end_seconds": end,
        "sample_count": len(selected),
        "maximum_absolute_difference_packets": max(absolute),
        "mean_absolute_difference_packets": sum(absolute) / len(absolute),
        "rmse_packets": math.sqrt(sum(value * value for value in differences) / len(differences)),
        "mean_signed_difference_packets": sum(differences) / len(differences),
        "start_difference_packets": differences[0],
        "end_difference_packets": differences[-1],
    }


def _first_exceedance(rows: list[dict[str, float]], threshold: float) -> int | None:
    return next(
        (int(row["time_seconds"]) for row in rows if abs(row["difference_packets"]) > threshold),
        None,
    )


def _least_squares_slope(rows: list[dict[str, float]]) -> float:
    xs = [row["time_seconds"] for row in rows]
    ys = [row["difference_packets"] for row in rows]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


def _write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_plots(
    output: Path,
    reference_times: list[float],
    reference_values: list[float],
    uc_times: list[int],
    uc_values: list[float],
    rows: list[dict[str, float]],
    quantity: str,
    plot_ymax: float,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1890, 1080
    background, grid, ink = "#FAFBFC", "#D9DEE5", "#263238"
    blue, orange, purple = "#0072B2", "#D55E00", "#7A3E9D"
    regular_font = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold_font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    font = ImageFont.truetype(regular_font, 27)
    small = ImageFont.truetype(regular_font, 23)
    title_font = ImageFont.truetype(bold_font, 35)

    def canvas(title: str, ylabel: str, ymin: float, ymax: float):
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        left, top, right, bottom = 165, 145, width - 70, height - 125
        draw.text((left, 35), title, fill=ink, font=title_font)
        for x_tick in range(0, 151, 25):
            x = left + (right - left) * x_tick / 150
            draw.line((x, top, x, bottom), fill=grid, width=2)
            label = str(x_tick)
            box = draw.textbbox((0, 0), label, font=small)
            draw.text((x - (box[2] - box[0]) / 2, bottom + 18), label, fill=ink, font=small)
        step = 10 if ymax - ymin > 20 else 1
        first_y = math.ceil(ymin / step) * step
        y_tick = first_y
        while y_tick <= ymax + 1e-9:
            y = bottom - (bottom - top) * (y_tick - ymin) / (ymax - ymin)
            draw.line((left, y, right, y), fill=grid, width=2)
            label = f"{y_tick:g}"
            box = draw.textbbox((0, 0), label, font=small)
            draw.text((left - 18 - (box[2] - box[0]), y - (box[3] - box[1]) / 2), label, fill=ink, font=small)
            y_tick += step
        draw.line((left, top, left, bottom), fill=ink, width=3)
        draw.line((left, bottom, right, bottom), fill=ink, width=3)
        x_label = "Time (s)"
        box = draw.textbbox((0, 0), x_label, font=font)
        draw.text(((left + right - (box[2] - box[0])) / 2, height - 55), x_label, fill=ink, font=font)
        draw.text((left, 93), ylabel, fill=ink, font=small)
        return image, draw, (left, top, right, bottom)

    def xy(bounds, time: float, value: float, ymin: float, ymax: float):
        left, top, right, bottom = bounds
        return (
            left + (right - left) * time / 150,
            bottom - (bottom - top) * (value - ymin) / (ymax - ymin),
        )

    image, draw, bounds = canvas(
        f"{quantity}: published digitisation and UC observation",
        f"{quantity} (packets)", 0, plot_ymax,
    )
    transition_x = xy(bounds, 50, 0, 0, plot_ymax)[0]
    draw.line((transition_x, bounds[1], transition_x, bounds[3]), fill="#555555", width=3)
    reference_points = [xy(bounds, time, value, 0, plot_ymax) for time, value in zip(reference_times, reference_values)]
    draw.line(reference_points, fill=orange, width=5, joint="curve")
    for x, y in reference_points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=orange)
    step_points = []
    for index, (time, value) in enumerate(zip(uc_times, uc_values)):
        point = xy(bounds, time, value, 0, plot_ymax)
        if index:
            step_points.append((point[0], step_points[-1][1]))
        step_points.append(point)
    draw.line(step_points, fill=blue, width=5, joint="curve")
    legend_x, legend_y = bounds[0] + 30, bounds[1] + 30
    for offset, color, label in (
        (0, orange, "de Souza Figure 5(a), digitised"),
        (42, blue, "Urban Cybernetics DT=1"),
        (84, "#555555", "Declared demand transition, 50 s"),
    ):
        draw.line((legend_x, legend_y + offset + 13, legend_x + 55, legend_y + offset + 13), fill=color, width=5)
        draw.text((legend_x + 70, legend_y + offset), label, fill=ink, font=small)
    image.save(output / "overlay.png", dpi=(180, 180))

    times = [row["time_seconds"] for row in rows]
    differences = [row["difference_packets"] for row in rows]
    ymin = math.floor(min(differences) - 0.5)
    ymax = math.ceil(max(differences) + 0.5)
    image, draw, bounds = canvas(
        "Difference at integer-second UC observations",
        "UC - digitised reference (packets)", ymin, ymax,
    )
    for threshold in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0):
        y = xy(bounds, 0, threshold, ymin, ymax)[1]
        draw.line((bounds[0], y, bounds[2], y), fill="#333333" if threshold == 0 else "#969DA6", width=3 if threshold == 0 else 2)
    transition_x = xy(bounds, 50, 0, ymin, ymax)[0]
    draw.line((transition_x, bounds[1], transition_x, bounds[3]), fill="#555555", width=3)
    points = [xy(bounds, time, value, ymin, ymax) for time, value in zip(times, differences)]
    draw.line(points, fill=purple, width=5, joint="curve")
    image.save(output / "difference.png", dpi=(180, 180))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--uc-result", type=Path, default=DEFAULT_UC_RESULT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--comparison-id", default="m8-desouza-figure5a-dt1-comparison-v1")
    parser.add_argument("--series-id", default="l1_cumulative_inflow")
    parser.add_argument("--quantity", default="L1 cumulative inflow")
    parser.add_argument("--plot-ymax", type=float, default=72.0)
    parser.add_argument("--stable-time-sort", action="store_true")
    parser.add_argument("--comparison-start", type=int)
    parser.add_argument("--comparison-end", type=int)
    args = parser.parse_args()

    reference_times, reference_values, reference_value_column, reference_time_quality = _load_reference(
        args.reference, stable_time_sort=args.stable_time_sort,
    )
    uc_times, uc_values, uc_result = _load_uc(args.uc_result, args.series_id)
    uc_by_time = dict(zip(uc_times, uc_values))
    comparison_start = args.comparison_start if args.comparison_start is not None else math.ceil(reference_times[0])
    comparison_end = args.comparison_end if args.comparison_end is not None else math.floor(reference_times[-1])
    if comparison_start < reference_times[0] or comparison_end > reference_times[-1]:
        raise ValueError("requested comparison grid lies outside digitised reference support")
    comparison_times = list(range(comparison_start, comparison_end + 1))
    rows = []
    for time in comparison_times:
        reference_value = _linear_interpolate(reference_times, reference_values, time)
        uc_value = uc_by_time[time]
        rows.append({
            "time_seconds": float(time),
            "uc_observed_packets": uc_value,
            "published_interpolated_reference_packets": reference_value,
            "difference_packets": uc_value - reference_value,
            "absolute_difference_packets": abs(uc_value - reference_value),
        })

    differences = [row["difference_packets"] for row in rows]
    absolute = [abs(value) for value in differences]
    post_rows = [row for row in rows if row["time_seconds"] >= 61]
    post_slope = _least_squares_slope(post_rows)
    uc_peak_value = max(uc_by_time[time] for time in comparison_times)
    uc_peak_time = next(time for time in comparison_times if uc_by_time[time] == uc_peak_value)
    reference_peak_value = max(reference_values)
    reference_peak_time = reference_times[reference_values.index(reference_peak_value)]
    reference_near_peak_points = [
        {"time_seconds": time, "value_packets": value}
        for time, value in zip(reference_times, reference_values)
        if reference_peak_value - value <= 0.01
    ]
    reference_decreases = [
        {
            "from_time_seconds": reference_times[index - 1],
            "to_time_seconds": reference_times[index],
            "change_packets": reference_values[index] - reference_values[index - 1],
        }
        for index in range(1, len(reference_values))
        if reference_values[index] < reference_values[index - 1]
    ]
    metrics = {
        "schema_version": "uc.validation.published-comparison.v1",
        "comparison_id": args.comparison_id,
        "case_id": uc_result["case_id"],
        "case_version": uc_result["case_version"],
        "uc_result_id": uc_result["result_id"],
        "quantity": args.quantity,
        "units": "packets",
        "reference_classification": "published digitised figure data; not ground truth",
        "interpolation": {
            "method": "piecewise linear interpolation of the digitised published series onto exact UC integer-second ticks",
            "uc_interpolated": False,
            "extrapolation": False,
            "comparison_support_seconds": [comparison_times[0], comparison_times[-1]],
            "comparison_sample_count": len(rows),
        },
        "source_integrity": {
            "digitised_csv_sha256": _sha256(args.reference),
            "uc_result_json_sha256": _sha256(args.uc_result),
            "digitised_point_count": len(reference_times),
            "digitised_value_column": reference_value_column,
            **reference_time_quality,
            "uc_point_count": len(uc_times),
            "digitised_value_decrease_count": len(reference_decreases),
            "digitised_value_decreases": reference_decreases,
        },
        "metrics": {
            "maximum_absolute_difference_packets": max(absolute),
            "maximum_absolute_difference_time_seconds": int(rows[absolute.index(max(absolute))]["time_seconds"]),
            "mean_absolute_difference_packets": sum(absolute) / len(absolute),
            "rmse_packets": math.sqrt(sum(value * value for value in differences) / len(differences)),
            "first_absolute_difference_exceeds_0_5_packets_seconds": _first_exceedance(rows, 0.5),
            "first_absolute_difference_exceeds_1_packet_seconds": _first_exceedance(rows, 1.0),
            "first_absolute_difference_exceeds_2_packets_seconds": _first_exceedance(rows, 2.0),
            "final_comparison_difference_packets": differences[-1],
            "final_comparison_time_seconds": comparison_times[-1],
            "post_transition_difference_slope_packets_per_second": post_slope,
            "post_transition_difference_change_packets": post_rows[-1]["difference_packets"] - post_rows[0]["difference_packets"],
            "uc_peak_packets": uc_peak_value,
            "uc_peak_time_seconds": uc_peak_time,
            "reference_peak_packets": reference_peak_value,
            "reference_peak_time_seconds": reference_peak_time,
            "peak_storage_difference_packets": uc_peak_value - reference_peak_value,
            "peak_timing_difference_seconds": uc_peak_time - reference_peak_time,
            "peak_timing_absolute_difference_seconds": abs(uc_peak_time - reference_peak_time),
            "reference_points_within_0_01_packets_of_peak": reference_near_peak_points,
        },
        "regions": {
            "initial_capacity_region": _summary(rows, comparison_times[0], 49),
            "transition_window": _summary(rows, 50, 60),
            "post_transition_low_demand_region": _summary(rows, 61, comparison_times[-1]),
        },
        "interpretation_rule": (
            "Drift is assessed observationally from the signed difference trajectory after the transition, "
            "including its least-squares slope and endpoint change; no fitted correction is applied."
        ),
        "provenance": [
            str(args.reference.resolve().relative_to(ROOT)),
            str(args.uc_result.resolve().relative_to(ROOT)),
            "UC evidence was read as persisted; the loading engine was not imported or executed.",
        ],
    }

    args.output.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output / "comparison_series.csv", rows)
    (args.output / "summary.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    _render_plots(
        args.output, reference_times, reference_values, uc_times, uc_values,
        rows, args.quantity, args.plot_ymax,
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
