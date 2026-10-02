// SPDX-License-Identifier: MPL-2.0
import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";
import type { CumulativeSeries } from "../lib/contract";

echarts.use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

export function ScientificChart({ series, tick }: { series: CumulativeSeries; tick: number }) {
  const elementRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!elementRef.current) return;
    const chart = echarts.init(elementRef.current, undefined, { renderer: "canvas" });
    const option = {
      animation: false,
      grid: { left: 44, right: 18, top: 28, bottom: 31 },
      tooltip: { trigger: "axis", backgroundColor: "#12231f", borderColor: "#385f54", textStyle: { color: "#e6f0ed" } },
      xAxis: { type: "category", data: series.ticks, name: "tick", boundaryGap: false, axisLabel: { color: "#78948b" }, axisLine: { lineStyle: { color: "#28443c" } } },
      yAxis: { type: "value", name: "packets", minInterval: 1, axisLabel: { color: "#78948b" }, splitLine: { lineStyle: { color: "rgba(89, 124, 115, .14)" } } },
      series: [
        { name: "cumulative entries", type: "line", step: "end", data: series.cumulative_entries, symbol: "none", lineStyle: { width: 2, color: "#5be4bd" }, itemStyle: { color: "#5be4bd" } },
        { name: "cumulative exits", type: "line", step: "end", data: series.cumulative_exits, symbol: "none", lineStyle: { width: 2, color: "#d8ff79" }, itemStyle: { color: "#d8ff79" }, markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: "#f6ad55", type: "dashed", opacity: .65 }, data: [{ xAxis: tick }] } },
        { name: "storage", type: "line", step: "end", data: series.storage_packets, symbol: "none", lineStyle: { width: 1.5, color: "#ffb55f", type: "dotted" }, itemStyle: { color: "#ffb55f" } },
      ],
    };
    chart.setOption(option);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(elementRef.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [series, tick]);
  return <div ref={elementRef} className="scientific-chart" aria-label={`Cumulative entry and exit curves for ${series.link_id}`} />;
}
