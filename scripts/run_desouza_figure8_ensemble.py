#!/usr/bin/env python3
"""Run and export the seeded de Souza Figure 8 validation ensemble."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from urban_cybernetics.canonical_validation.desouza_figure8 import (
    FIGURE8_SERIES_IDS,
    run_figure8_ensemble,
    summarise_figure8_ensemble,
)


ROOT = Path(__file__).resolve().parents[1]
DETERMINISTIC_RESULT = (
    ROOT / "fixtures/visualisation/validation/runs/"
    "m8-pub-dsouza-fig7-dt1-baseline-v1/result.json"
)
DEFAULT_SUMMARY = ROOT / "data/validation/desouza_figure8_ensemble_summary_v1.json"
DEFAULT_POINTWISE = ROOT / "data/validation/desouza_figure8_pointwise_v1.csv"
DEFAULT_REPLICATIONS = ROOT / "data/validation/desouza_figure8_replications_v1.csv"
DEFAULT_OUTPUT = ROOT / "outputs/validation/m8_desouza_figure8_ensemble_v1"
SELECTED_SEEDS = (0, 1, 2, 3, 4, 5, 10, 25, 50, 75, 99)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_path(path: Path) -> str:
    """Use repository-relative labels when possible, without restricting CLI output."""

    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_deterministic(path: Path) -> dict[str, tuple[float, ...]]:
    result = json.loads(path.read_text(encoding="utf-8"))
    available = {series["series_id"]: series for series in result["observed_series"]}
    return {
        series_id: tuple(available[series_id]["values"])
        for series_id in FIGURE8_SERIES_IDS
    }


def _write_pointwise(path: Path, pointwise: dict[str, list[dict[str, object]]]) -> None:
    rows = []
    for tick in range(121):
        row: dict[str, object] = {"tick": tick, "time_seconds": tick}
        for series_id in FIGURE8_SERIES_IDS:
            values = pointwise[series_id][tick]
            for metric in ("mean", "median", "minimum", "maximum", "p05", "p95", "deterministic"):
                row[f"{series_id}_{metric}"] = values[metric]
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_replications(path: Path, replications) -> None:
    rows = []
    for replication in replications:
        rows.append({
            "seed": replication.seed,
            "route_sequence": ",".join(replication.route_sequence),
            "route_sequence_sha256": replication.route_sequence_sha256,
            "route_count_l2": replication.route_count_l2,
            "route_count_l3": replication.route_count_l3,
            "route_share_l2": replication.route_share_l2,
            "route_share_l3": replication.route_share_l3,
            "final_Gu": replication.upstream_cumulative_outflow[-1],
            "final_F1": replication.downstream_1_cumulative_inflow[-1],
            "final_F2": replication.downstream_2_cumulative_inflow[-1],
            "event_count": replication.event_count,
            "conservation_check": replication.conservation_check,
            "fifo_check": replication.fifo_check,
            "identity_check": replication.identity_check,
            "cumulative_closure_check": replication.cumulative_closure_check,
            "physical_eligibility_check": replication.physical_eligibility_check,
            "replay_check": replication.replay_check,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _render_plots(output: Path, replications, summary: dict[str, object]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    _render_envelope(output / "ensemble_overlay.png", replications, summary)
    _render_endpoints(output / "endpoint_distributions.png", replications)


def _fonts():
    from PIL import ImageFont

    regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    return ImageFont.truetype(regular, 22), ImageFont.truetype(bold, 31)


def _render_envelope(path: Path, replications, summary: dict[str, object]) -> None:
    from PIL import Image, ImageDraw

    width, height = 1890, 1500
    image = Image.new("RGB", (width, height), "#FAFBFC")
    draw = ImageDraw.Draw(image, "RGBA")
    font, title_font = _fonts()
    draw.text((110, 32), "de Souza Figure 8 seeded diverge ensemble", fill="#263238", font=title_font)
    draw.text((110, 78), "100 replications; shaded 5th–95th percentile; black deterministic Figure 7(a)", fill="#455A64", font=font)
    colors = {
        "upstream_cumulative_outflow": (122, 62, 157),
        "downstream_1_cumulative_inflow": (0, 114, 178),
        "downstream_2_cumulative_inflow": (213, 94, 0),
    }
    labels = {
        "upstream_cumulative_outflow": "Gu — upstream cumulative outflow",
        "downstream_1_cumulative_inflow": "F1 — downstream link 1 cumulative inflow",
        "downstream_2_cumulative_inflow": "F2 — downstream link 2 cumulative inflow",
    }
    selected = {replication.seed: replication for replication in replications if replication.seed in SELECTED_SEEDS}
    for panel, series_id in enumerate(FIGURE8_SERIES_IDS):
        left, right = 125, width - 70
        top = 150 + panel * 430
        bottom = top + 350
        ymax = 70 if panel == 0 else 60 if panel == 1 else 25
        draw.text((left, top - 42), labels[series_id], fill="#263238", font=font)
        for x_tick in range(0, 121, 20):
            x = left + (right - left) * x_tick / 120
            draw.line((x, top, x, bottom), fill="#D9DEE5", width=2)
            draw.text((x - 10, bottom + 12), str(x_tick), fill="#455A64", font=font)
        y_step = 10 if ymax > 30 else 5
        for y_tick in range(0, ymax + 1, y_step):
            y = bottom - (bottom - top) * y_tick / ymax
            draw.line((left, y, right, y), fill="#D9DEE5", width=2)
            draw.text((left - 48, y - 10), str(y_tick), fill="#455A64", font=font)
        draw.line((left, top, left, bottom), fill="#263238", width=3)
        draw.line((left, bottom, right, bottom), fill="#263238", width=3)

        def xy(tick, value):
            return (
                left + (right - left) * tick / 120,
                bottom - (bottom - top) * value / ymax,
            )

        rows = summary["pointwise"][series_id]
        band = [xy(row["tick"], row["p95"]) for row in rows]
        band += [xy(row["tick"], row["p05"]) for row in reversed(rows)]
        color = colors[series_id]
        draw.polygon(band, fill=(*color, 42))
        for replication in selected.values():
            values = getattr(replication, series_id)
            draw.line([xy(tick, value) for tick, value in enumerate(values)], fill=(*color, 62), width=1)
        draw.line([xy(row["tick"], row["mean"]) for row in rows], fill=(*color, 255), width=5)
        draw.line([xy(row["tick"], row["deterministic"]) for row in rows], fill="#202124", width=3)
    image.save(path, dpi=(180, 180))


def _render_endpoints(path: Path, replications) -> None:
    from PIL import Image, ImageDraw

    width, height = 1890, 980
    image = Image.new("RGB", (width, height), "#FAFBFC")
    draw = ImageDraw.Draw(image)
    font, title_font = _fonts()
    draw.text((110, 32), "Figure 8 endpoint distributions", fill="#263238", font=title_font)
    draw.text((110, 78), "100 seeded replications; route assignment totals and 120 s cumulative inflows", fill="#455A64", font=font)
    panels = (
        ("Assigned routes to L2", [r.route_count_l2 for r in replications], "#0072B2"),
        ("Assigned routes to L3", [r.route_count_l3 for r in replications], "#D55E00"),
        ("Final F1 inflow", [r.downstream_1_cumulative_inflow[-1] for r in replications], "#0072B2"),
        ("Final F2 inflow", [r.downstream_2_cumulative_inflow[-1] for r in replications], "#D55E00"),
    )
    for index, (label, values, color) in enumerate(panels):
        col, row = index % 2, index // 2
        left = 110 + col * 900
        top = 155 + row * 390
        right, bottom = left + 790, top + 290
        draw.text((left, top - 36), label, fill="#263238", font=font)
        counts = {value: values.count(value) for value in range(min(values), max(values) + 1)}
        maximum = max(counts.values())
        bar_width = (right - left) / len(counts)
        for offset, (value, count) in enumerate(counts.items()):
            x0 = left + offset * bar_width + 2
            x1 = left + (offset + 1) * bar_width - 2
            y = bottom - (bottom - top) * count / maximum
            draw.rectangle((x0, y, x1, bottom), fill=color, outline="#263238", width=1)
            if offset % max(1, len(counts) // 6) == 0:
                draw.text((x0, bottom + 10), str(value), fill="#455A64", font=font)
        draw.line((left, bottom, right, bottom), fill="#263238", width=3)
        draw.line((left, top, left, bottom), fill="#263238", width=3)
        draw.text((right - 220, top + 8), f"mean {sum(values)/len(values):.2f}", fill="#263238", font=font)
    image.save(path, dpi=(180, 180))


def export(summary_path: Path, pointwise_path: Path, replications_path: Path, output: Path) -> dict[str, object]:
    deterministic = _load_deterministic(DETERMINISTIC_RESULT)
    replications = run_figure8_ensemble()
    full_summary = summarise_figure8_ensemble(replications, deterministic)
    pointwise = full_summary["pointwise"]
    _write_pointwise(pointwise_path, pointwise)
    _write_replications(replications_path, replications)
    _render_plots(output, replications, full_summary)
    persisted = {
        "schema_version": "uc.validation.stochastic-ensemble.v1",
        "ensemble_id": "m8-desouza-figure8-stochastic-diverge-v1",
        "case_id": "M8-PUB-DSOUZA-FIG8-DT1",
        "reference_case_id": "M8-PUB-DSOUZA-FIG7-DT1",
        "reference_result": str(DETERMINISTIC_RESULT.relative_to(ROOT)),
        "reference_result_sha256": _sha256(DETERMINISTIC_RESULT),
        "physical_fixture": {
            "length_m_by_link": {"L1": 150.0, "L2": 150.0, "L3": 150.0},
            "free_flow_speed_mps": 30.0,
            "backward_wave_speed_mps": 6.0,
            "jam_density_veh_per_m_by_link": {"L1": 0.2, "L2": 0.1, "L3": 0.1},
            "demand": "0.8 veh/s for t<50 s; 0.4 veh/s for 50<t<=120 s",
            "tick_duration_seconds": 1.0,
            "horizon_seconds": 120,
        },
        "replication_count": full_summary["replication_count"],
        "seeds": full_summary["seeds"],
        "seed_policy": full_summary["seed_policy"],
        "route_draw_policy": full_summary["route_draw_policy"],
        "selected_plot_seeds": list(SELECTED_SEEDS),
        "deterministic_coverage": full_summary["deterministic_coverage"],
        "ensemble_mean_deviation_from_deterministic": full_summary["ensemble_mean_deviation_from_deterministic"],
        "endpoint_distributions": full_summary["endpoint_distributions"],
        "route_distribution": full_summary["route_distribution"],
        "validation_gates": full_summary["validation_gates"],
        "artifacts": {
            "pointwise_csv": _artifact_path(pointwise_path),
            "replications_csv": _artifact_path(replications_path),
            "ensemble_overlay": _artifact_path(output / "ensemble_overlay.png"),
            "endpoint_distributions": _artifact_path(output / "endpoint_distributions.png"),
        },
        "replication_evidence": [asdict(replication) for replication in replications],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return persisted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--pointwise", type=Path, default=DEFAULT_POINTWISE)
    parser.add_argument("--replications", type=Path, default=DEFAULT_REPLICATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = export(args.summary, args.pointwise, args.replications, args.output)
    print(json.dumps({
        "ensemble_id": summary["ensemble_id"],
        "replication_count": summary["replication_count"],
        "validation_gates": summary["validation_gates"],
        "deterministic_coverage": summary["deterministic_coverage"],
        "artifacts": summary["artifacts"],
    }, indent=2))


if __name__ == "__main__":
    main()
