"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  PositionsPanel,
  FillsPanel,
  DecisionsPanel,
  AgentsPanel,
  RiskPanel,
  LearningPanel,
} from "@/components/dock/DockPanels";
import { useSnapshotStore } from "@/lib/qs/snapshot-store";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "positions", label: "持仓" },
  { key: "fills", label: "成交" },
  { key: "decisions", label: "决策" },
  { key: "agents", label: "组件" },
  { key: "risk", label: "风控" },
  { key: "learning", label: "学习" },
] as const;

const PANELS: Record<(typeof TABS)[number]["key"], React.ComponentType> = {
  positions: PositionsPanel,
  fills: FillsPanel,
  decisions: DecisionsPanel,
  agents: AgentsPanel,
  risk: RiskPanel,
  learning: LearningPanel,
};

export function BottomPanel() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("positions");
  const [open, setOpen] = useState(true);
  const agents = useSnapshotStore((s) => s.snap?.agents) ?? [];
  const Panel = PANELS[tab];

  return (
    <div className="flex flex-col border-t border-tv-border bg-tv-panel">
      <div className="flex items-center">
        <div className="flex">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => {
                setTab(key);
                setOpen(true);
              }}
              className={cn(
                "border-b-2 px-3.5 py-2 text-[11.5px] font-medium transition-colors",
                tab === key && open
                  ? "border-tv-blue text-tv-blue"
                  : "border-transparent text-tv-text-muted hover:text-tv-text",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-3 px-3 text-[10px] text-tv-text-dim">
          <span className="tabular-nums">{agents.length} 组件</span>
          <button
            onClick={() => setOpen((v) => !v)}
            className="rounded p-1 text-tv-text-muted hover:bg-tv-panel-hover hover:text-tv-text"
            aria-label={open ? "收起面板" : "展开面板"}
          >
            {open ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronUp className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
      {open && (
        <div className="h-56 overflow-auto border-t border-tv-border/60">
          <Panel />
        </div>
      )}
    </div>
  );
}
