"use client";

import { MousePointer2, Minus, Ruler, Trash2, Lock } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useChartStore, type DrawingTool } from "@/lib/store/chart-store";
import { cn } from "@/lib/utils";

interface ToolDef {
  key: DrawingTool;
  icon: typeof MousePointer2;
  label: string;
  hint?: string;
}

const TOOLS: ToolDef[] = [
  { key: "cursor", icon: MousePointer2, label: "光标", hint: "浏览模式" },
  {
    key: "hline",
    icon: Minus,
    label: "水平线",
    hint: "点击图表标记价位",
  },
  {
    key: "measure",
    icon: Ruler,
    label: "测量",
    hint: "点击两点测量价差、涨幅、K线数和成交量",
  },
];

const LOCKED = [
  { label: "趋势线" },
  { label: "Fibonacci" },
  { label: "文本" },
];

export function LeftSidebar() {
  const tool = useChartStore((s) => s.tool);
  const setTool = useChartStore((s) => s.setTool);
  const clearPriceLines = useChartStore((s) => s.clearPriceLines);
  const symbol = useChartStore((s) => s.symbol);

  return (
    <aside className="flex w-11 flex-col items-center gap-0.5 border-r border-tv-border bg-tv-panel py-1.5">
      {TOOLS.map((t) => {
        const Icon = t.icon;
        const active = tool === t.key;
        return (
          <Tooltip key={t.key}>
            <TooltipTrigger
              onClick={() => setTool(t.key)}
              aria-label={t.label}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded transition-colors hover:bg-tv-panel-hover",
                active
                  ? "bg-tv-blue/15 text-tv-blue"
                  : "text-tv-text-muted hover:text-tv-text",
              )}
            >
              <Icon className="h-4 w-4" />
            </TooltipTrigger>
            <TooltipContent side="right" className="text-xs">
              <div className="font-medium">{t.label}</div>
              {t.hint && (
                <div className="mt-0.5 text-[10px] text-tv-text-muted">{t.hint}</div>
              )}
            </TooltipContent>
          </Tooltip>
        );
      })}

      <Tooltip>
        <TooltipTrigger
          onClick={() => clearPriceLines(symbol)}
          aria-label="清除画线"
          className="flex h-8 w-8 items-center justify-center rounded text-tv-text-muted hover:bg-tv-panel-hover hover:text-tv-red"
        >
          <Trash2 className="h-4 w-4" />
        </TooltipTrigger>
        <TooltipContent side="right" className="text-xs">
          <div className="font-medium">清除画线</div>
          <div className="mt-0.5 text-[10px] text-tv-text-muted">
            清除该标的的所有画线
          </div>
        </TooltipContent>
      </Tooltip>

      <div className="my-1 h-px w-6 bg-tv-border" />

      {LOCKED.map((t) => (
        <Tooltip key={t.label}>
          <TooltipTrigger
            disabled
            aria-label={t.label}
            className="flex h-8 w-8 cursor-not-allowed items-center justify-center rounded text-tv-text-dim opacity-40"
          >
            <Lock className="h-3.5 w-3.5" />
          </TooltipTrigger>
          <TooltipContent side="right" className="text-xs">
            <div className="font-medium">{t.label}</div>
            <div className="mt-0.5 text-[10px] text-tv-yellow">
              即将上线
            </div>
          </TooltipContent>
        </Tooltip>
      ))}
    </aside>
  );
}
