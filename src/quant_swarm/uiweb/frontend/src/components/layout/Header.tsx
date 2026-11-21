"use client";

import { SymbolSelector } from "@/components/chart/SymbolSelector";
import { TimeframeSelector } from "@/components/chart/TimeframeSelector";
import { IndicatorMenu } from "@/components/chart/IndicatorMenu";
import { Separator } from "@/components/ui/separator";
import { useSnapshotStore } from "@/lib/qs/snapshot-store";

export function Header() {
  const agents = useSnapshotStore((s) => s.snap?.agents) ?? [];
  const now = Date.now() / 1000;
  const online = agents.filter(
    (a) => now - new Date(a.ts).getTime() / 1000 < 20,
  ).length;

  return (
    <header className="flex h-12 items-center justify-between border-b border-tv-border bg-tv-panel px-3">
      <div className="flex items-center gap-1">
        <SymbolSelector />
        <Separator orientation="vertical" className="h-6 bg-tv-border" />
        <TimeframeSelector />
        <Separator orientation="vertical" className="mx-1 h-6 bg-tv-border" />
        <IndicatorMenu />
      </div>

      <div className="flex items-center gap-2 text-[11px] text-tv-text-muted">
        <span
          className={
            "inline-flex h-1.5 w-1.5 rounded-full " +
            (online ? "bg-tv-green" : "bg-tv-red")
          }
        />
        <span className="tabular-nums">
          {online}/{agents.length} agents online
        </span>
      </div>
    </header>
  );
}
