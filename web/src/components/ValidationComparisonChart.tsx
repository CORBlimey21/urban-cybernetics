// SPDX-License-Identifier: MPL-2.0
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ValidationCase, ValidationResult } from "../lib/contract";

echarts.use([LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

export function ValidationComparisonChart({ validationCase, result, tick, storageKey, labSeries }: { validationCase: ValidationCase; result: ValidationResult; tick: number; storageKey?: string; labSeries?: { label: string; ticks: number[]; values: number[]; units: string; provenance: string } | null }) {
  const selectable = validationCase.expected_series.length ? validationCase.expected_series : result.observed_series;
  const [seriesId, setSeriesId] = useState(selectable[0]?.series_id ?? "");
  const elementRef = useRef<HTMLDivElement>(null);
  const expected = useMemo(() => validationCase.expected_series.find((item) => item.series_id === seriesId), [validationCase, seriesId]);
  const observed = useMemo(() => result.observed_series.find((item) => item.series_id === seriesId), [result, seriesId]);
  const difference = useMemo(() => result.difference_series.find((item) => item.series_id === seriesId), [result, seriesId]);

  useEffect(() => {
    const remembered = storageKey ? window.localStorage.getItem(storageKey) : null;
    const next = selectable.some((item) => item.series_id === remembered)
      ? remembered!
      : selectable[0]?.series_id ?? "";
    setSeriesId(next);
  }, [storageKey, validationCase, result]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (storageKey && selectable.some((item) => item.series_id === seriesId)) window.localStorage.setItem(storageKey, seriesId);
  }, [seriesId, storageKey, selectable]);

  useEffect(() => {
    if (!elementRef.current || !observed) return;
    const chart = echarts.init(elementRef.current, undefined, { renderer: "canvas" });
    const differenceExtent = difference ? Math.max(1, ...difference.values.map((value) => Math.abs(value))) : 1;
    chart.setOption({
      animationDuration: 260, animationDurationUpdate: 180,
      grid: { left: 52, right: 54, top: 44, bottom: 40 },
      legend: { top: 8, textStyle: { color: "#8ea79f", fontSize: 9 } },
      tooltip: { trigger: "axis", axisPointer: { type: "cross", lineStyle: { color: "#708d83" } }, backgroundColor: "#12231f", borderColor: "#385f54", textStyle: { color: "#e6f0ed", fontSize: 10 } },
      xAxis: { type: "category", data: observed.ticks, name: observed.time_basis.includes("ordinal") ? "packet ordinal" : "tick", boundaryGap: false, axisLabel: { color: "#78948b" }, axisLine: { lineStyle: { color: "#28443c" } } },
      yAxis: [
        { type: "value", name: observed.units, scale: true, minInterval: observed.units === "packets" || observed.units === "ticks" ? 1 : undefined, axisLabel: { color: "#78948b" }, splitLine: { lineStyle: { color: "rgba(89,124,115,.14)" } } },
        ...(difference ? [{ type: "value", name: "difference", min: -differenceExtent, max: differenceExtent, interval: differenceExtent, axisLabel: { color: "#c98989" }, splitLine: { show: false }, axisLine: { show: true, lineStyle: { color: "rgba(255,143,143,.35)" } } }] : []),
      ],
      series: [
        ...(expected ? [{ name: "expected · analytical", type: "line", step: "end", data: expected.values, symbol: "circle", symbolSize: 5, lineStyle: { width: 2, color: "#d8ff79", type: "dashed" }, itemStyle: { color: "#d8ff79" } }] : []),
        { name: "observed · Python", type: "line", step: "end", data: observed.values, symbol: "none", lineStyle: { width: 3, color: "#5be4bd" }, itemStyle: { color: "#5be4bd" }, markLine: { silent: true, symbol: "none", label: { show: true, formatter: `t${tick}`, color: "#ffcf91", fontSize: 9 }, lineStyle: { color: "#ffb55f", type: "dotted" }, data: [{ xAxis: tick }] } },
        ...(difference ? [{ name: "observed − expected", type: "line", yAxisIndex: 1, step: "end", data: difference.values, symbol: "diamond", symbolSize: 5, lineStyle: { width: 2, color: "#ff8f8f" }, areaStyle: { color: "rgba(255,143,143,.09)" }, itemStyle: { color: "#ff8f8f" } }] : []),
        ...(labSeries && labSeries.units === observed.units ? [{ name: `${labSeries.label} · Lab Bench`, type: "line", step: "end", data: observed.ticks.map((observedTick) => labSeries.values[labSeries.ticks.indexOf(observedTick)] ?? null), symbol: "triangle", symbolSize: 6, lineStyle: { width: 2, color: "#b9a4ff", type: "dotted" }, itemStyle: { color: "#b9a4ff" } }] : []),
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(elementRef.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [difference, expected, labSeries, observed, tick]);

  return <div className="validation-chart-wrap"><label>{expected ? "Comparison quantity" : "Observed quantity"}<select value={seriesId} onChange={(event) => setSeriesId(event.target.value)}>{selectable.map((series) => <option key={series.series_id} value={series.series_id}>{series.label}</option>)}</select>{labSeries && <span className="source-chip">Lab export · {labSeries.provenance.replaceAll("_", " ")}</span>}</label><div ref={elementRef} className="validation-comparison-chart" aria-label={expected ? `Expected versus observed ${expected.label}` : `Observed ${observed?.label ?? "validation series"}`} /><div className="chart-source">{expected ? "Expected: analytical/reference · Observed: Python validation projection · Difference: validation output" : "Observed only: Python validation projection · Published comparison intentionally absent"} · Lab export: explicit presentation overlay</div></div>;
}
