import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import * as React from "react";
import { Button } from "@/components/ui/primitives";
import { Download, Maximize2 } from "lucide-react";
import type { NetworkGraphData } from "@/types";

const COLORS: Record<string, string> = {
  self: "#22d3ee",
  contact: "#60a5fa",
  group: "#a78bfa",
  topic: "#2dd4bf",
};

export function NetworkGraph({
  data,
  onSelect,
  height = 560,
}: {
  data: NetworkGraphData;
  onSelect?: (node: NetworkGraphData["nodes"][number] | null) => void;
  height?: number;
}) {
  const container = React.useRef<HTMLDivElement>(null);
  const core = React.useRef<Core | null>(null);

  const elements = React.useMemo<ElementDefinition[]>(() => {
    const maxWeight = Math.max(1, ...data.nodes.map((node) => node.weight));
    const nodes: ElementDefinition[] = data.nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.label,
        kind: node.kind,
        size: 22 + Math.sqrt(node.weight / maxWeight) * 34,
        color: COLORS[node.kind] ?? COLORS.contact,
      },
    }));
    const edges: ElementDefinition[] = data.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        kind: edge.kind,
        inferred: edge.inferred,
        width: 0.8 + Math.log2(1 + edge.weight) * 0.7,
        label: edge.label,
      },
    }));
    return [...nodes, ...edges];
  }, [data]);

  React.useEffect(() => {
    if (!container.current) return;
    const instance = cytoscape({
      container: container.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            width: "data(size)",
            height: "data(size)",
            label: "data(label)",
            "font-size": 9,
            color: "#b6c2d2",
            "text-valign": "bottom",
            "text-margin-y": 4,
            "border-width": 2,
            "border-color": "#0b0f14",
            "text-outline-width": 2,
            "text-outline-color": "#0b0f14",
          },
        },
        {
          selector: "node[kind = 'group']",
          style: { shape: "round-rectangle", width: "data(size)", height: "data(size)" },
        },
        {
          selector: "node[kind = 'topic']",
          style: { shape: "diamond" },
        },
        {
          selector: "edge",
          style: {
            width: "data(width)",
            "line-color": "#33475f",
            "curve-style": "bezier",
            opacity: 0.85,
          },
        },
        {
          selector: "edge[inferred = true]",
          style: { "line-style": "dashed", "line-color": "#2dd4bf", opacity: 0.45 },
        },
        { selector: "edge[kind = 'membership']", style: { "line-color": "#4b6280" } },
        { selector: "node:selected", style: { "border-color": "#22d3ee", "border-width": 3 } },
        { selector: ".faded", style: { opacity: 0.15 } },
      ],
      layout: { name: "cose", animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 90 },
      wheelSensitivity: 0.2,
      minZoom: 0.25,
      maxZoom: 2.4,
    });
    instance.on("tap", "node", (event) => {
      const id = event.target.id() as string;
      onSelect?.(data.nodes.find((node) => node.id === id) ?? null);
    });
    instance.on("tap", (event) => {
      if (event.target === instance) onSelect?.(null);
    });
    core.current = instance;
    return () => {
      instance.destroy();
      core.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements]);

  const exportPng = () => {
    if (!core.current) return;
    const blob = core.current.png({ full: true, scale: 2 });
    const link = document.createElement("a");
    link.href = blob;
    link.download = "relationship-network.png";
    link.click();
  };

  return (
    <div className="relative">
      <div ref={container} style={{ height }} className="w-full rounded-xl bg-[rgb(var(--bg))]" />
      <div className="absolute right-2 top-2 flex gap-1.5">
        <Button size="sm" variant="ghost" onClick={() => core.current?.fit(undefined, 40)}>
          <Maximize2 className="h-3.5 w-3.5" /> Fit
        </Button>
        <Button size="sm" variant="ghost" onClick={exportPng}>
          <Download className="h-3.5 w-3.5" /> PNG
        </Button>
      </div>
      <div className="pointer-events-none absolute bottom-2 left-3 flex flex-wrap gap-3 text-[10px] text-muted">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-[#22d3ee]" /> owner
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-[#60a5fa]" /> contact
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-[#a78bfa]" /> group
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-[2px] w-5 bg-[#33475f]" /> observed
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-[2px] w-5 border-t border-dashed border-[#2dd4bf]" /> inferred
        </span>
      </div>
    </div>
  );
}
