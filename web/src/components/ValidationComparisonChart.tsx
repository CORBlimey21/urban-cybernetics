import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ValidationCase, ValidationResult } from "../lib/contract";

echarts.use([LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

export function ValidationComparisonChart({ validationCase, result, tick }: { validationCase: ValidationCase; result: ValidationResult; tick: number }) {
  const [seriesId, setSeriesId] = useState(validationCase.expected_series[0]?.series_id ?? "");
  const elementRef = useRef<HTMLDivElement>(null);
  const expected = useMemo(() => validationCase.expected_series.find((item) => item.series_id === seriesId), [validationCase, seriesId]);
  const observed = useMemo(() => result.observed_series.find((item) => item.series_id === seriesId), [result, seriesId]);
  const difference = useMemo(() => result.difference_series.find((item) => item.series_id === seriesId), [result, seriesId]);

  useEffect(() => {
    if (!elementRef.current || !expected || !observed || !difference) return;
    const chart = echarts.init(elementRef.current, undefined, { renderer: "canvas" });
    chart.setOption({
      animationDuration: 260,
      grid: { left: 48, right: 18, top: 42, bottom: 36 },
      legend: { top: 8, textStyle: { color: "#8ea79f", fontSize: 9 } },
      tooltip: { trigger: "axis", backgroundColor: "#12231f", borderColor: "#385f54", textStyle: { color: "#e6f0ed" } },
      xAxis: { type: "category", data: expected.ticks, name: expected.time_basis.includes("ordinal") ? "packet ordinal" : "tick", boundaryGap: false, axisLabel: { color: "#78948b" }, axisLine: { lineStyle: { color: "#28443c" } } },
      yAxis: { type: "value", name: expected.units, minInterval: expected.units === "packets" || expected.units === "ticks" ? 1 : undefined, axisLabel: { color: "#78948b" }, splitLine: { lineStyle: { color: "rgba(89,124,115,.14)" } } },
      series: [
        { name: "expected · analytical", type: "line", step: "end", data: expected.values, symbol: "circle", symbolSize: 5, lineStyle: { width: 2, color: "#d8ff79", type: "dashed" }, itemStyle: { color: "#d8ff79" } },
        { name: "observed · Python", type: "line", step: "end", data: observed.values, symbol: "none", lineStyle: { width: 3, color: "#5be4bd" }, itemStyle: { color: "#5be4bd" }, markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: "#ffb55f", type: "dotted" }, data: [{ xAxis: tick }] } },
        { name: "observed − expected", type: "line", step: "end", data: difference.values, symbol: "none", lineStyle: { width: 1.5, color: "#ff8f8f" }, itemStyle: { color: "#ff8f8f" } },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(elementRef.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [difference, expected, observed, tick]);

  return <div className="validation-chart-wrap"><label>Comparison quantity<select value={seriesId} onChange={(event) => setSeriesId(event.target.value)}>{validationCase.expected_series.map((series) => <option key={series.series_id} value={series.series_id}>{series.label}</option>)}</select></label><div ref={elementRef} className="validation-comparison-chart" aria-label={`Expected versus observed ${expected?.label ?? "validation series"}`} /><div className="chart-source">Expected: analytical/reference · Observed: Python validation projection · Difference: validation output</div></div>;
}
