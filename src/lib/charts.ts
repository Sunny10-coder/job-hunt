import type { ChartOption } from "@/components/charts/Chart";
import { num } from "./format";

export const PALETTE = {
  accent: "#22d3ee",
  teal: "#2dd4bf",
  amber: "#f59e0b",
  danger: "#ef4444",
  violet: "#a78bfa",
  blue: "#60a5fa",
  muted: "#7c8ba1",
  grid: "rgba(148,163,184,0.14)",
};

function isLight(): boolean {
  return document.documentElement.dataset.theme === "light";
}

function textColor(): string {
  return isLight() ? "#475569" : "#8ba0b8";
}

const axis = () => ({
  axisLine: { lineStyle: { color: PALETTE.grid } },
  axisTick: { show: false },
  axisLabel: { color: textColor(), fontSize: 10 },
  splitLine: { lineStyle: { color: PALETTE.grid } },
});

const tooltip = () => ({
  backgroundColor: isLight() ? "#ffffff" : "#111823",
  borderColor: isLight() ? "#d6dfea" : "#1f2a37",
  borderWidth: 1,
  padding: [7, 10] as [number, number],
  textStyle: { color: isLight() ? "#0f172a" : "#e6edf5", fontSize: 11 },
  extraCssText: "border-radius:10px;box-shadow:0 12px 30px -12px rgba(0,0,0,.6);",
});

export function barOption(
  labels: string[],
  values: number[],
  opts: { color?: string; name?: string; horizontal?: boolean; height?: number } = {},
): ChartOption {
  const color = opts.color ?? PALETTE.accent;
  return {
    animationDuration: 350,
    grid: { left: 44, right: 12, top: 18, bottom: 34, containLabel: false },
    tooltip: { ...tooltip(), trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: opts.horizontal
      ? { type: "value", ...axis(), splitLine: { lineStyle: { color: PALETTE.grid } } }
      : { type: "category", data: labels, ...axis(), splitLine: { show: false } },
    yAxis: opts.horizontal
      ? { type: "category", data: labels, ...axis(), splitLine: { show: false } }
      : { type: "value", ...axis() },
    series: [
      {
        name: opts.name ?? "Messages",
        type: "bar",
        data: values,
        barMaxWidth: 22,
        itemStyle: { color, borderRadius: [3, 3, 0, 0] },
        emphasis: { itemStyle: { color: PALETTE.teal } },
      },
    ],
  };
}

export function lineOption(
  labels: string[],
  values: number[],
  opts: { color?: string; name?: string; area?: boolean } = {},
): ChartOption {
  const color = opts.color ?? PALETTE.teal;
  return {
    animationDuration: 350,
    grid: { left: 44, right: 14, top: 18, bottom: 34 },
    tooltip: { ...tooltip(), trigger: "axis" },
    xAxis: { type: "category", data: labels, boundaryGap: false, ...axis(), splitLine: { show: false } },
    yAxis: { type: "value", ...axis() },
    series: [
      {
        name: opts.name ?? "Messages",
        type: "line",
        data: values,
        smooth: 0.25,
        showSymbol: labels.length < 40,
        symbolSize: 4,
        lineStyle: { width: 2, color },
        itemStyle: { color },
        areaStyle:
          opts.area === false
            ? undefined
            : {
                color: {
                  type: "linear",
                  x: 0,
                  y: 0,
                  x2: 0,
                  y2: 1,
                  colorStops: [
                    { offset: 0, color: `${color}55` },
                    { offset: 1, color: `${color}05` },
                  ],
                },
              },
      },
    ],
  };
}

export function heatmapOption(grid: number[][], weekdays: string[], hours: string[]): ChartOption {
  const data: [number, number, number][] = [];
  let max = 0;
  grid.forEach((row, y) => {
    row.forEach((value, x) => {
      data.push([x, y, value]);
      max = Math.max(max, value);
    });
  });
  return {
    animationDuration: 300,
    grid: { left: 52, right: 12, top: 10, bottom: 46 },
    tooltip: {
      ...tooltip(),
      formatter: (params: unknown) => {
        const item = params as { value: [number, number, number] };
        return `${weekdays[item.value[1]]} ${hours[item.value[0]]}:00 — ${num(item.value[2])} messages`;
      },
    },
    xAxis: {
      type: "category",
      data: hours.map((hour) => `${hour}:00`),
      ...axis(),
      splitLine: { show: false },
      axisLabel: { color: textColor(), fontSize: 9, interval: 1 },
    },
    yAxis: {
      type: "category",
      data: weekdays.map((day) => day.slice(0, 3)),
      ...axis(),
      splitLine: { show: false },
    },
    visualMap: {
      min: 0,
      max: Math.max(1, max),
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemWidth: 10,
      itemHeight: 80,
      textStyle: { color: textColor(), fontSize: 9 },
      inRange: { color: ["#0d2b34", "#155e6b", "#22d3ee"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        progressive: 2000,
        itemStyle: { borderColor: isLight() ? "#ffffff" : "#0b0f14", borderWidth: 2, borderRadius: 3 },
        emphasis: { itemStyle: { borderColor: PALETTE.teal, borderWidth: 1 } },
      },
    ],
  };
}

export function pieOption(items: { name: string; value: number }[], colors?: string[]): ChartOption {
  return {
    animationDuration: 300,
    tooltip: { ...tooltip(), trigger: "item" },
    legend: {
      bottom: 0,
      textStyle: { color: textColor(), fontSize: 10 },
      itemWidth: 8,
      itemHeight: 8,
      icon: "circle",
    },
    color: colors ?? [PALETTE.accent, PALETTE.teal, PALETTE.amber, PALETTE.violet, PALETTE.danger],
    series: [
      {
        type: "pie",
        radius: ["52%", "78%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: isLight() ? "#fff" : "#0b0f14", borderWidth: 2 },
        label: { show: false },
        data: items,
      },
    ],
  };
}

export function stackedBarsOption(
  labels: string[],
  series: { name: string; values: number[]; color: string }[],
): ChartOption {
  return {
    animationDuration: 300,
    grid: { left: 44, right: 12, top: 26, bottom: 34 },
    tooltip: { ...tooltip(), trigger: "axis" },
    legend: { top: 0, textStyle: { color: textColor(), fontSize: 10 }, itemWidth: 8, itemHeight: 8 },
    xAxis: { type: "category", data: labels, ...axis(), splitLine: { show: false } },
    yAxis: { type: "value", ...axis() },
    series: series.map((item) => ({
      name: item.name,
      type: "bar" as const,
      stack: "total",
      data: item.values,
      itemStyle: { color: item.color },
      barMaxWidth: 26,
    })),
  };
}
