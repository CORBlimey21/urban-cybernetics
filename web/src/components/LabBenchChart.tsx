// SPDX-License-Identifier: MPL-2.0
import { LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";
import type { LabColumn, ValidationCase } from "../lib/contract";

echarts.use([LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

export function LabBenchChart({ columns, ticks, kind, validationCase }: { columns: LabColumn[]; ticks: number[]; kind: "line" | "step" | "scatter"; validationCase: ValidationCase }) {
  const elementRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!elementRef.current) return;
    const chart = echarts.init(elementRef.current, undefined, { renderer: "canvas" });
    chart.setOption({
      animationDuration: 180,
      grid: { left: 48, right: 24, top: 42, bottom: 42 },
      legend: { top: 8, textStyle: { color: "#91aaa2", fontSize: 9 } },
      tooltip: { trigger: "axis", backgroundColor: "#12231f", borderColor: "#385f54", textStyle: { color: "#e6f0ed", fontSize: 10 } },
      xAxis: { type: "category", name: "physical tick", data: ticks, axisLabel: { color: "#78948b" }, axisLine: { lineStyle: { color: "#28443c" } } },
      yAxis: { type: "value", name: [...new Set(columns.map((item) => item.units))].join(" / "), axisLabel: { color: "#78948b" }, splitLine: { lineStyle: { color: "rgba(89,124,115,.14)" } } },
      series: columns.map((column, index) => ({
        name: `${column.label} · ${column.kind.replaceAll("_", " ")}`, type: kind === "scatter" ? "scatter" : "line",
        step: kind === "step" ? "end" : false, data: column.values, symbolSize: kind === "scatter" ? 7 : 4,
        lineStyle: { width: 2, color: ["#d8ff79", "#5be4bd", "#ffb55f", "#b9a4ff"][index % 4] },
        itemStyle: { color: ["#d8ff79", "#5be4bd", "#ffb55f", "#b9a4ff"][index % 4] },
        markLine: index === 0 ? { silent: true, symbol: "none", label: { color: "#d4b7ff", fontSize: 8 }, lineStyle: { color: "#806da9", type: "dotted" }, data: validationCase.overlays.map((item) => ({ xAxis: item.active_from_tick, name: item.label })) } : undefined,
      })),
    });
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(elementRef.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [columns, kind, ticks, validationCase]);
  return <div ref={elementRef} className="lab-chart" aria-label="Lab Bench selected series graph" />;
}
