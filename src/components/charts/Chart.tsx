import { BarChart, HeatmapChart, LineChart, PieChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import * as React from "react";
import { cn } from "@/lib/format";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export type ChartOption = echarts.EChartsCoreOption;

const registry = new Map<HTMLDivElement, echarts.ECharts>();

export function Chart({
  option,
  height = 240,
  className,
  onClick,
}: {
  option: ChartOption;
  height?: number | string;
  className?: string;
  onClick?: (params: { name?: string; value?: unknown; dataIndex?: number }) => void;
}) {
  const container = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!container.current) return;
    const instance = echarts.init(container.current, undefined, { renderer: "canvas" });
    registry.set(container.current, instance);
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      instance.dispose();
      if (container.current) registry.delete(container.current);
    };
  }, []);

  React.useEffect(() => {
    if (!container.current) return;
    const instance = registry.get(container.current);
    instance?.setOption(option, true);
  }, [option]);

  React.useEffect(() => {
    if (!container.current || !onClick) return;
    const instance = registry.get(container.current);
    if (!instance) return;
    const handler = (params: { name?: string; value?: unknown; dataIndex?: number }) => onClick(params);
    instance.on("click", handler);
    return () => {
      instance.off("click", handler);
    };
  }, [onClick]);

  return (
    <div
      ref={container}
      className={cn("w-full", className)}
      style={{ height: typeof height === "number" ? `${height}px` : height }}
    />
  );
}

export function disposeAllCharts() {
  registry.forEach((instance) => instance.dispose());
  registry.clear();
}
